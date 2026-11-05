"""3단계: 마스킹.

- PII 좌표: 검은 박스(cv2.rectangle, 채움)로 원본 픽셀을 덮어쓴다.
- Fail-closed: 마지막 OCR 검증 프레임과 달라진 영역은 OCR이 다시 확인할 때까지 모자이크.
  (OCR이 송출보다 느려서, 새로 뜬 개인정보가 검증 전에 송출되는 것을 막는다.)
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

import cv2
import numpy as np

from .detect import Hit

DIFF_SCALE = 0.5
DIFF_THRESHOLD = 10
MOSAIC_BLOCK = 18


def diff_key(bgr: np.ndarray) -> np.ndarray:
    small = cv2.resize(bgr, None, fx=DIFF_SCALE, fy=DIFF_SCALE, interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)


def black_boxes(frame: np.ndarray, hits: list[Hit]) -> None:
    h, w = frame.shape[:2]
    for hit in hits:
        x0, y0, x1, y1 = hit.box
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(w - 1, x1), min(h - 1, y1)
        if x1 > x0 and y1 > y0:
            cv2.rectangle(frame, (x0, y0), (x1, y1), (0, 0, 0), thickness=-1)


def mosaic(frame: np.ndarray, x: int, y: int, w: int, h: int) -> None:
    roi = frame[y:y + h, x:x + w]
    if roi.size == 0:
        return
    sw, sh = max(1, w // MOSAIC_BLOCK), max(1, h // MOSAIC_BLOCK)
    small = cv2.resize(roi, (sw, sh), interpolation=cv2.INTER_AREA)
    roi[:] = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)


def _regions(cur_key: np.ndarray, ref_key: np.ndarray, factor: float) -> list[tuple[int, int, int, int]]:
    diff = cv2.absdiff(cur_key, ref_key)
    _, mask = cv2.threshold(diff, DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=3)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [tuple(int(v * factor) for v in cv2.boundingRect(c)) for c in contours]


def pending_regions(frame: np.ndarray, ref_key: np.ndarray) -> list[tuple[int, int, int, int]]:
    """원본 해상도 frame 기준 변경 영역."""
    return _regions(diff_key(frame), ref_key, 1 / DIFF_SCALE)


# ---------- 스크롤 보정 ----------
# 스크롤하면 화면 전체가 '바뀐 영역'이 되어, 전체 OCR이 끝날 때까지 화면이 멈춘 것처럼 보였다.
# 화면이 세로로 dy만큼 밀린 것을 찾으면, 검증된 기준 화면·PII 박스·검증본을 같이 밀고
# 새로 드러난 띠만 검증 대기로 둔다. 밀어도 맞지 않는 곳(고정 헤더 등)은 그대로 '바뀐 영역'이라
# Fail-closed는 유지된다.
SCROLL_MIN_STD = 12.0    # 템플릿 띠의 최소 명암 편차 (빈 여백이면 위치를 못 잡으므로 포기)
SCROLL_MAX_ERR = 0.05    # 정규화 제곱오차 허용치 (이보다 크면 스크롤이 아니라고 본다)
SCROLL_CANDIDATES = 4  # 1/4 해상도에서 고르는 후보 위치 수


SCROLL_MIN_ROWS = 0.25   # 바뀐 줄 비율이 이보다 작으면 스크롤 검사 생략


def changed_rows_ratio(cur: np.ndarray, ref: np.ndarray) -> float:
    """비교 이미지에서 픽셀이 바뀐 줄의 비율 (0~1)."""
    return float(np.count_nonzero((cv2.absdiff(cur, ref) > DIFF_THRESHOLD).any(axis=1))) / max(1, cur.shape[0])


_ref_cache: list = [None, None, None]  # [기준, 1/2, 1/4 크기] — 같은 검증본이면 다시 줄이지 않는다


def _half(img: np.ndarray) -> np.ndarray:
    return cv2.resize(img, (img.shape[1] // 2, img.shape[0] // 2), interpolation=cv2.INTER_AREA)


def estimate_scroll(cur: np.ndarray, ref: np.ndarray) -> int:
    """회색조 비교 이미지에서 cur[y] ≈ ref[y - dy] 인 dy를 찾는다. 스크롤이 아니면 0."""
    h = cur.shape[0]
    if ref.shape != cur.shape or h < 64:
        return 0
    if _ref_cache[0] is not ref:
        half = _half(ref)
        _ref_cache[:] = [ref, half, _half(half)]
    ref_s, ref_q, cur_s = _ref_cache[1], _ref_cache[2], _half(cur)
    hs = cur_s.shape[0]
    bhs = max(8, hs // 12)
    # 줄별 누적합으로 각 가로 띠의 명암 편차(무늬가 얼마나 많은지)를 빠르게 구한다
    rows = cur_s.astype(np.float32)
    c_sum = np.concatenate(([0], np.cumsum(rows.sum(axis=1))))
    c_sq = np.concatenate(([0], np.cumsum((rows * rows).sum(axis=1))))
    n = bhs * cur_s.shape[1]

    def sd(y: int) -> float:
        mean = (c_sum[y + bhs] - c_sum[y]) / n
        return max(0.0, (c_sq[y + bhs] - c_sq[y]) / n - mean * mean) ** 0.5

    starts = range(0, hs - bhs, max(1, bhs // 2))
    # 화면을 4등분해 구간마다 템플릿 띠를 하나씩 고르고, 가운데 구간부터 차례로 시도한다.
    #  - 아래로 스크롤하면 위쪽 내용이, 위로 스크롤하면 아래쪽 내용이 이전 화면에 남아 있다
    #  - 고른 띠가 새로 드러났거나 새로 뜬 내용이면 맞지 않으므로 다음 구간 띠로 다시 찾는다
    quarter = lambda y: min(3, (y + bhs // 2) * 4 // hs)  # noqa: E731
    for q in (1, 2, 0, 3):
        group = [y for y in starts if quarter(y) == q]
        if not group:
            continue
        ys = max(group, key=sd)
        if sd(ys) < SCROLL_MIN_STD:  # 빈 여백이면 위치를 못 잡는다
            continue
        tpl_s = cur_s[ys:ys + bhs]
        if cv2.absdiff(tpl_s, ref_s[ys:ys + bhs]).mean() < 1.0:  # 그 자리 그대로인 띠는 판단 불가
            continue
        best_y = _match_band(cur, ref, ref_q, tpl_s, ys * 2, bhs * 2)
        if best_y is not None:
            dy = ys * 2 - best_y
            return dy if 0 < abs(dy) < 0.8 * h else 0
    return 0


def _match_band(cur, ref, ref_q, tpl_s, y0: int, bh: int) -> int | None:
    """cur[y0:y0+bh] 띠가 ref의 어느 y에 있는지. 충분히 맞는 곳이 없으면 None.
    1) 1/4 해상도에서 후보 위치 몇 개 → 2) 원래 해상도에서 후보마다 ±8px 정밀 비교
    (글자 줄이 비슷하게 반복되는 화면은 1/4 해상도에서 엉뚱한 줄과 헷갈릴 수 있어 후보를 여럿 본다)"""
    h = cur.shape[0]
    tpl_q = _half(tpl_s)[:, :ref_q.shape[1]]
    coarse = cv2.matchTemplate(ref_q, tpl_q, cv2.TM_SQDIFF_NORMED)[:, 0]
    cands: list[int] = []
    for c in np.argsort(coarse):
        if all(abs(int(c) - p) > 3 for p in cands):
            cands.append(int(c))
            if len(cands) == SCROLL_CANDIDATES:
                break
    tpl = cur[y0:y0 + bh]
    t_sq = cv2.norm(tpl, cv2.NORM_L2SQR) or 1.0
    best_err, best_y = 1.0, None
    seen: set[int] = set()
    for c in cands:
        for y in range(max(0, c * 4 - 8), min(h - bh, c * 4 + 8) + 1):
            if y in seen:
                continue
            seen.add(y)
            a = ref[y:y + bh]
            # TM_SQDIFF_NORMED와 같은 값. 위치 수가 적어 matchTemplate보다 직접 계산이 훨씬 빠르다
            err = cv2.norm(a, tpl, cv2.NORM_L2SQR) / ((cv2.norm(a, cv2.NORM_L2SQR) or 1.0) * t_sq) ** 0.5
            if err < best_err:
                best_err, best_y = err, y
    return best_y if best_err <= SCROLL_MAX_ERR else None


def shift_rows(a: np.ndarray, dy: int, fill: np.ndarray | None = None) -> np.ndarray:
    """a를 세로로 dy만큼 민다. 새로 드러난 줄은 fill(같은 크기)에서, 없으면 0으로 채운다."""
    out = fill.copy() if fill is not None else np.zeros_like(a)
    if dy > 0:
        out[dy:] = a[:-dy]
    elif dy < 0:
        out[:dy] = a[-dy:]
    return out


def exposed_rows(dy: int, h: int) -> tuple[int, int]:
    """dy만큼 스크롤했을 때 새로 드러난 줄 범위 [y0, y1)."""
    return (0, min(h, dy)) if dy > 0 else (max(0, h + dy), h)


def shift_hits(hits: list[Hit], dy: int, height: int, grow: int = 2) -> list[Hit]:
    """PII 박스를 dy만큼 옮긴다. 위치 추정 오차를 감안해 grow만큼 넓히고, 화면 밖은 버린다."""
    out = []
    for h in hits:
        x0, y0, x1, y1 = h.box
        y0, y1 = y0 + dy - grow, y1 + dy + grow
        if y1 <= 0 or y0 >= height:
            continue
        out.append(Hit(h.kind, (max(0, x0 - grow), max(0, y0), x1 + grow, min(height, y1))))
    return out


def scale_hits(hits: list[Hit], s: float) -> list[Hit]:
    if s == 1:
        return hits
    return [Hit(h.kind, (int(h.box[0] * s), int(h.box[1] * s), int(h.box[2] * s) + 1, int(h.box[3] * s) + 1))
            for h in hits]


@dataclass
class Verified:
    """OCR이 끝난 프레임의 결과.
    masked_frame: 검사를 통과한 프레임에 검은 박스를 이미 칠한 사본 (원본 PII 없음)."""
    seq: int = -1
    ref_key: np.ndarray | None = None
    hits: list[Hit] = field(default_factory=list)
    latency_ms: float = 0.0
    masked_frame: np.ndarray | None = None


class VerifiedState:
    def __init__(self):
        self._lock = threading.Lock()
        self._v = Verified()
        self.version = 0  # 검증 결과가 바뀔 때마다 증가 → 화면이 멈춰 있어도 송출 갱신

    def set(self, v: Verified) -> None:
        with self._lock:
            self._v = v
            self.version += 1

    def get(self) -> Verified:
        with self._lock:
            return self._v


def mask_frame(frame: np.ndarray, v: Verified) -> tuple[np.ndarray, int]:
    """frame을 제자리에서 마스킹한다. 반환: (frame, 검증 대기 영역 수).

    frame은 원본 해상도여도 되고, 송출용으로 미리 축소한 이미지여도 된다.
    (축소본이면 마스킹·비교 연산량이 크게 준다. 좌표는 비교 기준 크기로 환산.)
    """
    if v.ref_key is None:  # 아직 한 번도 검증 안 됨 → 전체 가림
        h, w = frame.shape[:2]
        mosaic(frame, 0, 0, w, h)
        return frame, 1
    kh, kw = v.ref_key.shape
    fh, fw = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if gray.shape != (kh, kw):
        gray = cv2.resize(gray, (kw, kh), interpolation=cv2.INTER_AREA)

    ref, hits = v.ref_key, v.hits
    held = v.masked_frame if v.masked_frame is not None and v.masked_frame.shape == frame.shape else None
    band = None  # 스크롤로 새로 드러난 띠 (frame 좌표)
    # 스크롤이면 글자가 있는 줄 대부분이 바뀐다. 바뀐 줄이 적으면(타이핑, 일부 갱신) 스크롤 계산(3~7ms)을 건너뛴다
    dy = estimate_scroll(gray, v.ref_key) if changed_rows_ratio(gray, v.ref_key) >= SCROLL_MIN_ROWS else 0
    if dy:
        # 검증된 기준·박스·검증본을 스크롤만큼 같이 민다 → 화면이 멈추지 않고 따라 움직인다
        ref = shift_rows(v.ref_key, dy, gray)  # 드러난 줄은 band로 따로 가리므로 비교에서 제외
        hits = shift_hits(v.hits, round(dy / DIFF_SCALE), round(kh / DIFF_SCALE))
        dy_f = round(dy * fh / kh)
        if held is not None:
            held = shift_rows(held, dy_f)
        band = exposed_rows(dy_f, fh)
        band_px = frame[band[0]:band[1]].copy()  # 마스킹 전 원본 (모자이크용)

    regions = _regions(gray, ref, fw / kw)  # 마스킹 전 픽셀로 변경 영역 계산
    black_boxes(frame, scale_hits(hits, fw / (kw / DIFF_SCALE)))
    for x, y, w, h in regions:
        if held is not None:
            # 검사 중인 영역은 직전 검증본(이미 마스킹됨)으로 덮어 '잠깐 멈춘' 것처럼 보이게
            frame[y:y + h, x:x + w] = held[y:y + h, x:x + w]
        else:
            mosaic(frame, x, y, w, h)  # 검증본이 없을 때만 모자이크
    if band is not None and band[1] > band[0]:
        # 새로 드러난 띠는 아직 아무도 본 적 없는 내용 → OCR이 확인할 때까지 모자이크 (보통 0.1~0.2초)
        frame[band[0]:band[1]] = band_px
        mosaic(frame, 0, band[0], fw, band[1] - band[0])
    return frame, len(regions) + (1 if band else 0)
