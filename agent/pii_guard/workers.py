"""1~4단계 스레드."""
from __future__ import annotations

import collections
import logging
import queue
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

from .config import Config
from .detect import Hit, detect
from .masker import DIFF_SCALE, Verified, VerifiedState, black_boxes, diff_key, mask_frame
from .ring import RingBuffer

log = logging.getLogger("pii_guard")


class Rate:
    """최근 1초 동안의 처리 횟수."""

    def __init__(self):
        self._t: collections.deque[float] = collections.deque()
        self._lock = threading.Lock()

    def tick(self) -> None:
        now = time.perf_counter()
        with self._lock:
            self._t.append(now)
            while self._t and now - self._t[0] > 1.0:
                self._t.popleft()

    def value(self) -> float:
        now = time.perf_counter()
        with self._lock:
            while self._t and now - self._t[0] > 1.0:
                self._t.popleft()
            return float(len(self._t))


@dataclass
class AuditItem:
    jpeg: bytes
    kinds: list[str]
    box_count: int
    width: int
    height: int
    ts: float


class Stats:
    def __init__(self):
        self.capture = Rate()
        self.output = Rate()
        self.ocr = Rate()
        self.pending_regions = 0
        self.ocr_ready = False
        self.last_kinds: list[str] = []
        self.last_detect_at: float | None = None
        self.audit_uploaded = 0
        self.audit_failed = 0
        self.audit_enabled = False
        # 원격 on/off. 꺼지면 캡처·송출을 멈춘다 (OCR은 새 프레임이 없으니 자연히 쉼)
        self.sharing = threading.Event()
        self.sharing.set()


# ---------- 1단계: 캡처 (CPU, mss) ----------
def _mss(mod):
    return getattr(mod, "MSS", None)() if hasattr(mod, "MSS") else mod.mss()


def capture_rect(cfg: Config) -> dict:
    import mss

    with _mss(mss) as sct:
        mon = sct.monitors[cfg.monitor]
    if cfg.region:
        l, t, w, h = cfg.region
        return {"left": l, "top": t, "width": w, "height": h}
    return {"left": mon["left"], "top": mon["top"], "width": mon["width"], "height": mon["height"]}


def _dxcam_grabber(cfg: Config, rect: dict):
    """Windows Desktop Duplication API (dxcam). 화면이 안 바뀌면 None을 돌려줘 CPU를 아낀다."""
    import dxcam
    import mss

    with _mss(mss) as sct:
        mon = sct.monitors[cfg.monitor]
    l, t = rect["left"] - mon["left"], rect["top"] - mon["top"]
    region = (l, t, l + rect["width"], t + rect["height"])
    cam = dxcam.create(output_idx=cfg.monitor - 1, output_color="BGR")
    if cam is None:
        raise RuntimeError("dxcam 출력 장치를 찾지 못함")
    return lambda: cam.grab(region=region), cam


def capture_loop(cfg: Config, rect: dict, ring: RingBuffer, stats: Stats, stop: threading.Event) -> None:
    import mss

    period = 1.0 / cfg.fps
    grab, cam = None, None
    if cfg.capture_backend in ("auto", "dxcam"):
        try:
            grab, cam = _dxcam_grabber(cfg, rect)
            log.info("캡처: dxcam (Desktop Duplication)")
        except Exception as ex:
            log.warning("dxcam 사용 불가 → mss 사용 (%s)", ex)
    if grab is not None:
        while not stop.is_set():
            if not stats.sharing.is_set():  # 원격 꺼짐 → 화면을 읽지 않음
                time.sleep(0.1)
                continue
            t0 = time.perf_counter()
            frame = grab()
            if frame is not None:  # 화면이 바뀐 경우에만 덮어쓰기
                ring.write(frame)
                del frame
            stats.capture.tick()
            time.sleep(max(0.0, period - (time.perf_counter() - t0)))
        return
    log.info("캡처: mss (GDI)")
    with _mss(mss) as sct:  # mss 인스턴스는 스레드마다 따로 만들어야 한다
        while not stop.is_set():
            if not stats.sharing.is_set():  # 원격 꺼짐 → 화면을 읽지 않음
                time.sleep(0.1)
                continue
            t0 = time.perf_counter()
            shot = sct.grab(rect)
            bgra = np.frombuffer(shot.raw, dtype=np.uint8).reshape(shot.height, shot.width, 4)
            ring.write(bgra[:, :, :3])
            del shot, bgra
            stats.capture.tick()
            time.sleep(max(0.0, period - (time.perf_counter() - t0)))


# ---------- 2단계: OCR + Regex (GPU 가능 시 GPU) ----------
def _ocr_process_main(conn, langs: list[str], want_gpu: bool, threads: int, scale: float) -> None:
    """별도 프로세스에서 EasyOCR 실행. 무거운 OCR이 캡처/송출 스레드의 CPU·GIL을 뺏지 않는다."""
    import easyocr
    import torch

    gpu = want_gpu and torch.cuda.is_available()
    if not gpu:
        torch.set_num_threads(threads)
    reader = easyocr.Reader(langs, gpu=gpu, verbose=False)
    conn.send(("ready", gpu))
    while True:
        job = conn.recv()
        if job is None:
            break
        hits: list[Hit] = []
        for img, y_off in job:
            hits += _ocr(reader, img, scale, y_off)
        del job
        if gpu:
            torch.cuda.empty_cache()  # 캐시 반환 (VRAM 내용 0 초기화를 보장하지는 않음)
        conn.send(hits)


class OcrWorker:
    """OCR 프로세스와 파이프로 통신. 화면 조각을 보내고 PII 좌표만 돌려받는다."""

    def __init__(self, cfg: Config):
        import multiprocessing as mp

        ctx = mp.get_context("spawn")
        self._conn, child = ctx.Pipe()
        self._proc = ctx.Process(target=_ocr_process_main, name="pii-ocr", daemon=True,
                                 args=(child, cfg.ocr_langs, cfg.ocr_gpu, cfg.ocr_threads, cfg.ocr_scale))
        self._proc.start()
        log.info("EasyOCR 로딩 중 (별도 프로세스, langs=%s)", cfg.ocr_langs)
        _, gpu = self._conn.recv()
        log.info("EasyOCR 준비 완료 (gpu=%s, threads=%d)", gpu, cfg.ocr_threads)

    def run(self, strips: list[tuple[np.ndarray, int]]) -> list[Hit]:
        self._conn.send(strips)
        return self._conn.recv()

    def close(self) -> None:
        try:
            self._conn.send(None)
        except Exception:
            pass
        self._proc.join(timeout=3)
        if self._proc.is_alive():
            self._proc.kill()


STRIP_UP = 120    # 바뀐 영역 위쪽 여유 (위 줄의 라벨 포함, 원본 픽셀 기준)
STRIP_DOWN = 40
FULL_OCR_RATIO = 0.6  # 바뀐 띠가 화면의 60% 이상이면 전체 OCR


def _strips(regions, hits: list[Hit], height: int) -> list[tuple[int, int]]:
    """바뀐 영역을 화면 전체 폭의 가로 띠 (y0, y1)로 바꾸고 겹치면 합친다.
    라벨-값이 같은 줄에 있으므로 가로는 전체 폭으로 잘라야 라벨 문맥이 살아 있다."""
    spans = sorted((max(0, y - STRIP_UP), min(height, y + h + STRIP_DOWN)) for _, y, _, h in regions)
    merged: list[list[int]] = []
    for y0, y1 in spans:
        if merged and y0 <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], y1)
        else:
            merged.append([y0, y1])
    # 띠 경계에 걸친 기존 PII 박스는 통째로 다시 읽도록 띠를 넓힌다
    for m in merged:
        for hb in hits:
            if hb.box[1] < m[1] and hb.box[3] > m[0]:
                m[0], m[1] = max(0, min(m[0], hb.box[1] - 8)), min(height, max(m[1], hb.box[3] + 8))
    return [(a, b) for a, b in merged]


def _ocr(reader, img: np.ndarray, sc: float, y_off: int) -> list[Hit]:
    small = img if sc >= 1 else cv2.resize(img, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
    results = reader.readtext(small)
    hits = detect(results, pad=max(2, round(6 * sc)))
    del results, small  # 인식된 텍스트(평문 PII)는 좌표만 뽑은 뒤 바로 버린다
    k = 1 / sc if sc < 1 else 1.0
    return [Hit(h.kind, (round(h.box[0] * k), round(h.box[1] * k) + y_off,
                         round(h.box[2] * k), round(h.box[3] * k) + y_off)) for h in hits]


def ocr_loop(cfg: Config, ring: RingBuffer, state: VerifiedState, stats: Stats,
             audit_q: "queue.Queue[AuditItem]", stop: threading.Event) -> None:
    from .masker import pending_regions

    ocr = OcrWorker(cfg)
    try:
        _ocr_main_loop(cfg, ring, state, stats, audit_q, stop, ocr, pending_regions)
    finally:
        ocr.close()


def _ocr_main_loop(cfg, ring, state, stats, audit_q, stop, ocr, pending_regions) -> None:
    seq = -1
    while not stop.is_set():
        seq, frame = ring.read_latest(after=seq)
        if frame is None:
            continue
        prev = state.get()
        h = frame.shape[0]
        cur_key = diff_key(frame)

        if prev.ref_key is None:
            strips = [(0, h)]
        else:
            regions = pending_regions(frame, prev.ref_key)
            if not regions:  # 검증된 상태와 같음 → OCR 생략 (CPU 절약)
                frame.fill(0)
                del frame
                time.sleep(0.03)
                continue
            strips = _strips(regions, prev.hits, h)
            if sum(b - a for a, b in strips) > FULL_OCR_RATIO * h:
                strips = [(0, h)]

        t0 = time.perf_counter()
        if strips == [(0, h)]:
            hits = ocr.run([(frame, 0)])
            ref_key = cur_key
        else:
            # 띠 밖의 기존 결과는 유지, 띠 안은 새로 OCR
            hits = [x for x in prev.hits if not any(x.box[1] < b and x.box[3] > a for a, b in strips)]
            ref_key = prev.ref_key.copy()  # 띠 밖은 옛 기준 유지 (서서히 바뀌는 화면도 결국 감지)
            hits += ocr.run([(frame[a:b], a) for a, b in strips])
            for a, b in strips:
                ka, kb = int(a * DIFF_SCALE), int(b * DIFF_SCALE)
                ref_key[ka:kb] = cur_key[ka:kb]

        masked = frame.copy()
        black_boxes(masked, hits)  # 검증한 바로 그 프레임을 마스킹 → 송출보류용 + 감사로그용
        held = masked if cfg.stream_scale >= 1 else cv2.resize(
            masked, None, fx=cfg.stream_scale, fy=cfg.stream_scale, interpolation=cv2.INTER_AREA)
        state.set(Verified(seq=seq, ref_key=ref_key, hits=hits,
                           latency_ms=(time.perf_counter() - t0) * 1000,
                           masked_frame=held))  # 송출 해상도로 보관
        stats.ocr.tick()
        stats.ocr_ready = True

        if hits:
            kinds = sorted({x.kind for x in hits})
            stats.last_kinds, stats.last_detect_at = kinds, time.time()
            if stats.audit_enabled:
                ok, jpg = cv2.imencode(".jpg", masked, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ok:
                    try:
                        audit_q.put_nowait(AuditItem(jpg.tobytes(), kinds, len(hits),
                                                     masked.shape[1], masked.shape[0], time.time()))
                    except queue.Full:
                        pass
        frame.fill(0)  # 복사본 원본 픽셀 덮어쓰기 (최선의 노력)
        del frame


# ---------- 3단계 + 4단계(송출): 마스킹 → JPEG ----------
class LatestJpeg:
    def __init__(self):
        self._cond = threading.Condition()
        self._jpeg: bytes | None = None
        self._n = 0

    def put(self, jpeg: bytes) -> None:
        with self._cond:
            self._jpeg, self._n = jpeg, self._n + 1
            self._cond.notify_all()

    def wait(self, after: int, timeout: float = 2.0) -> tuple[int, bytes | None]:
        with self._cond:
            self._cond.wait_for(lambda: self._n > after, timeout)
            return self._n, self._jpeg


def _off_jpeg(ring: RingBuffer, scale: float) -> bytes:
    h, w = ring.shape
    h, w = max(1, int(h * min(scale, 1))), max(1, int(w * min(scale, 1)))
    img = np.full((h, w, 3), 24, np.uint8)
    text = "REMOTE OFF"
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 2)
    cv2.putText(img, text, ((w - tw) // 2, (h + th) // 2), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (200, 200, 200), 2)
    return cv2.imencode(".jpg", img)[1].tobytes()


def output_loop(cfg: Config, ring: RingBuffer, state: VerifiedState, out: LatestJpeg,
                stats: Stats, stop: threading.Event) -> None:
    """송출 해상도로 먼저 줄인 뒤 마스킹 → JPEG. 원본 해상도 연산을 하지 않아 빠르다."""
    seq, seen_version = -1, -1
    params = [cv2.IMWRITE_JPEG_QUALITY, cfg.jpeg_quality]
    was_sharing = True
    while not stop.is_set():
        if not stats.sharing.is_set():
            if was_sharing:  # 꺼진 순간 '원격 꺼짐' 화면을 한 번 내보내 마지막 화면이 남지 않게
                out.put(_off_jpeg(ring, cfg.stream_scale))
                was_sharing = False
                stats.pending_regions = 0
            time.sleep(0.1)
            continue
        if not was_sharing:  # 다시 켜짐 → 최신 프레임으로 즉시 다시 그림
            was_sharing, seen_version = True, -1
        # 새 프레임이 없어도 검증 결과가 바뀌면(보류 → 확정) 화면을 다시 그린다
        force = state.version != seen_version
        new_seq, frame = ring.read_latest_resized(cfg.stream_scale, after=-1 if force else seq, timeout=0.05)
        if frame is None:
            continue
        seq = new_seq
        seen_version = state.version
        masked, pending = mask_frame(frame, state.get())
        stats.pending_regions = pending
        ok, jpg = cv2.imencode(".jpg", masked, params)
        del frame, masked
        if ok:
            out.put(jpg.tobytes())  # 마스킹된 결과물만 송출 버퍼로 간다
            stats.output.tick()


# ---------- 4단계(감사 로그): 데몬 스레드 → Supabase ----------
def audit_loop(cfg: Config, audit_q: "queue.Queue[AuditItem]", stats: Stats, stop: threading.Event) -> None:
    import requests

    base = cfg.supabase_url
    headers = {"apikey": cfg.supabase_key, "Authorization": f"Bearer {cfg.supabase_key}"}
    last_kinds: list[str] = []
    last_at = 0.0
    http = requests.Session()
    while not stop.is_set():
        try:
            item = audit_q.get(timeout=1.0)
        except queue.Empty:
            continue
        # 같은 개인정보가 계속 떠 있는 동안 반복 업로드하지 않는다
        if item.kinds == last_kinds and item.ts - last_at < cfg.audit_interval:
            continue
        path = f"{cfg.session_id}/{time.strftime('%Y%m%d', time.localtime(item.ts))}/{int(item.ts * 1000)}.jpg"
        try:
            r = http.post(f"{base}/storage/v1/object/{cfg.audit_bucket}/{path}", data=item.jpeg,
                          headers={**headers, "Content-Type": "image/jpeg", "x-upsert": "false"}, timeout=15)
            r.raise_for_status()
            r = http.post(f"{base}/rest/v1/pii_audit_logs", timeout=15,
                          headers={**headers, "Content-Type": "application/json", "Prefer": "return=minimal"},
                          json={"session_id": cfg.session_id, "pii_types": item.kinds,
                                "box_count": item.box_count, "image_path": path,
                                "frame_width": item.width, "frame_height": item.height,
                                "detected_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(item.ts))})
            r.raise_for_status()
            stats.audit_uploaded += 1
            last_kinds, last_at = item.kinds, item.ts
            log.info("감사 로그 업로드: %s %s", item.kinds, path)
        except Exception as ex:  # 네트워크 오류가 화면 송출을 멈추게 하면 안 된다
            stats.audit_failed += 1
            log.warning("감사 로그 업로드 실패: %s", getattr(ex, "response", None) and ex.response.text or ex)
