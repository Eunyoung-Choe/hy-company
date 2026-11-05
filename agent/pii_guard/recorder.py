"""녹화: 마스킹이 끝난 송출 화면만 MP4로 저장한다.

- 원본 화면은 녹화하지 않는다. output_loop가 마스킹을 마친 프레임만 offer()로 넘긴다.
- 화면이 바뀔 때만 프레임이 오기 때문에, 별도 스레드가 일정한 간격(fps)으로
  가장 최근 프레임을 써서 영상 길이가 실제 시간과 같게 만든다.
- 인코더: imageio-ffmpeg(H.264, 브라우저에서도 재생) → 없으면 OpenCV mp4v(Windows 플레이어용).
"""
from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger("pii_guard")

NAME_RE = re.compile(r"^pii-\d{8}-\d{6}\.mp4$")  # 다운로드 시 경로 조작 방지용


class _FfmpegWriter:
    def __init__(self, path: Path, size: tuple[int, int], fps: int):
        import imageio_ffmpeg

        self._gen = imageio_ffmpeg.write_frames(
            str(path), size, fps=fps, codec="libx264", pix_fmt_in="bgr24", pix_fmt_out="yuv420p",
            quality=None, bitrate=None, macro_block_size=2,
            output_params=["-preset", "veryfast", "-crf", "23", "-movflags", "+faststart"])
        self._gen.send(None)
        self.codec = "H.264"

    def write(self, bgr: np.ndarray) -> None:
        self._gen.send(np.ascontiguousarray(bgr).tobytes())

    def close(self) -> None:
        self._gen.close()


class _CvWriter:
    def __init__(self, path: Path, size: tuple[int, int], fps: int):
        self._w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
        if not self._w.isOpened():
            raise RuntimeError("OpenCV VideoWriter(mp4v) 열기 실패")
        self.codec = "MPEG-4 (mp4v)"

    def write(self, bgr: np.ndarray) -> None:
        self._w.write(bgr)

    def close(self) -> None:
        self._w.release()


def _open_writer(path: Path, size: tuple[int, int], fps: int):
    try:
        return _FfmpegWriter(path, size, fps)
    except Exception as ex:
        log.warning("H.264 녹화 불가 → mp4v로 저장 (%s)", ex)
        return _CvWriter(path, size, fps)


class Recorder:
    def __init__(self, out_dir: Path, fps: int):
        self.out_dir, self.fps = out_dir, fps
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._started_at: float | None = None
        self._path: Path | None = None
        self.last_file: str | None = None
        self.error: str | None = None

    @property
    def recording(self) -> bool:
        return self._thread is not None

    def offer(self, masked_bgr: np.ndarray) -> None:
        """송출 직전의 마스킹 완성본을 받는다 (녹화 중이 아니면 무시)."""
        if self._thread is not None:
            with self._lock:
                self._frame = masked_bgr

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            self.out_dir.mkdir(parents=True, exist_ok=True)
            self._path = self.out_dir / time.strftime("pii-%Y%m%d-%H%M%S.mp4")
            self._frame, self.error = None, None
            self._stop.clear()
            self._started_at = time.time()
            self._thread = threading.Thread(target=self._run, args=(self._path,), name="recorder", daemon=True)
            self._thread.start()
        log.info("녹화 시작: %s", self._path.name)

    def stop(self) -> str | None:
        with self._lock:
            t, path = self._thread, self._path
        if t is None:
            return self.last_file
        self._stop.set()
        t.join(timeout=10)
        with self._lock:
            self._thread, self._started_at, self._frame = None, None, None
            if path and path.exists() and path.stat().st_size > 0:
                self.last_file = path.name
                log.info("녹화 저장: %s (%.1f MB)", path, path.stat().st_size / 1e6)
            elif not self.error:
                self.error = "녹화된 화면이 없습니다"
        return self.last_file

    def elapsed(self) -> float:
        s = self._started_at
        return 0.0 if s is None else time.time() - s

    def _run(self, path: Path) -> None:
        writer, size = None, None
        period = 1.0 / self.fps
        next_t = time.perf_counter()
        try:
            while not self._stop.is_set():
                with self._lock:
                    frame = self._frame
                if frame is not None:
                    if writer is None:  # 첫 프레임 크기로 고정 (H.264는 짝수 크기 필요)
                        h, w = frame.shape[:2]
                        size = (w - w % 2, h - h % 2)
                        writer = _open_writer(path, size, self.fps)
                        log.info("녹화 인코더: %s %dx%d %dfps", writer.codec, size[0], size[1], self.fps)
                    if (frame.shape[1], frame.shape[0]) != size:  # 원격 꺼짐 화면 등 크기가 다르면 맞춘다
                        frame = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
                    writer.write(frame)
                next_t += period
                delay = next_t - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                elif delay < -1.0:  # 크게 밀리면 따라잡지 말고 기준 시각을 다시 잡는다
                    next_t = time.perf_counter()
        except Exception as ex:
            self.error = f"녹화 실패: {ex}"
            log.exception("녹화 실패")
        finally:
            if writer is not None:
                writer.close()
