"""실행: agent 폴더에서  .venv\\Scripts\\python -m pii_guard"""
from __future__ import annotations

import logging
import queue
import signal
import threading
import time
from pathlib import Path

from .config import Config, load_env_file
from .masker import VerifiedState
from .recorder import Recorder
from .ring import RingBuffer
from .server import make_server
from .workers import (LatestJpeg, Stats, audit_loop, capture_loop, capture_rect,
                      ocr_loop, output_loop)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("pii_guard")
    load_env_file(Path(__file__).resolve().parent.parent / ".env")
    cfg = Config.from_env()

    rect = capture_rect(cfg)
    ring = RingBuffer(cfg.ring_slots, rect["height"], rect["width"])
    state = VerifiedState()
    stats = Stats()
    stats.audit_enabled = bool(cfg.supabase_url and cfg.supabase_key)
    out = LatestJpeg()
    audit_q: queue.Queue = queue.Queue(maxsize=8)
    stop = threading.Event()
    recorder = Recorder(cfg.record_dir, cfg.record_fps)

    def set_sharing(on: bool) -> None:
        if on:
            stats.sharing.set()
        else:
            stats.sharing.clear()
        log.info("원격 %s", "켜짐" if on else "꺼짐")

    def status() -> dict:
        v = state.get()
        return {
            "sharing": stats.sharing.is_set(),
            "capture_fps": stats.capture.value(),
            "output_fps": stats.output.value(),
            "ocr_fps": stats.ocr.value(),
            "ocr_latency_ms": round(v.latency_ms),
            "ocr_ready": stats.ocr_ready,
            "masked_boxes": len(v.hits),
            "pending_regions": stats.pending_regions,
            "last_kinds": stats.last_kinds,
            "last_detect_at": stats.last_detect_at,
            "audit_enabled": stats.audit_enabled,
            "audit_uploaded": stats.audit_uploaded,
            "audit_failed": stats.audit_failed,
            "capture_rect": rect,
            "recording": recorder.recording,
            "recording_sec": round(recorder.elapsed()),
            "last_recording": recorder.last_file,
            "recording_error": recorder.error,
        }

    threads = [
        threading.Thread(target=capture_loop, args=(cfg, rect, ring, stats, stop), name="capture", daemon=True),
        threading.Thread(target=ocr_loop, args=(cfg, ring, state, stats, audit_q, stop), name="ocr", daemon=True),
        threading.Thread(target=output_loop, args=(cfg, ring, state, out, stats, stop, recorder), name="output", daemon=True),
    ]
    if stats.audit_enabled:
        threads.append(threading.Thread(target=audit_loop, args=(cfg, audit_q, stats, stop),
                                        name="audit", daemon=True))
    else:
        log.warning("SUPABASE_URL / SUPABASE_SECRET_KEY 가 없어 감사 로그 업로드를 끕니다.")
    for t in threads:
        t.start()

    srv = make_server(cfg.stream_host, cfg.stream_port, out, status, set_sharing, cfg.allowed_origins, recorder)
    threading.Thread(target=srv.serve_forever, name="http", daemon=True).start()
    log.info("캡처 영역 %s", rect)
    log.info("송출: http://%s:%d/stream.mjpg  상태: /status", cfg.stream_host, cfg.stream_port)

    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        while not stop.is_set():
            time.sleep(0.5)
    finally:
        stop.set()
        recorder.stop()  # 녹화 중에 종료해도 MP4가 깨지지 않게 마무리
        srv.shutdown()
        ring.wipe()
        log.info("종료: Ring Buffer 를 0으로 덮어썼습니다.")


if __name__ == "__main__":
    main()
