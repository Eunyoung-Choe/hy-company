"""1단계 저장소: Ring Buffer A.

미리 할당한 numpy 슬롯에 새 프레임을 덮어쓴다(np.copyto). 파일로 저장하지 않는다.
슬롯 수만큼 지나면 가장 오래된 원본 픽셀은 새 프레임으로 덮여 사라진다.
"""
from __future__ import annotations

import threading

import cv2
import numpy as np


class RingBuffer:
    def __init__(self, slots: int, height: int, width: int):
        self._buf = np.zeros((slots, height, width, 3), dtype=np.uint8)
        self._seq = np.full(slots, -1, dtype=np.int64)
        self._next = 0
        self._latest = -1
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)

    @property
    def shape(self) -> tuple[int, int]:
        return self._buf.shape[1], self._buf.shape[2]

    def write(self, bgr: np.ndarray) -> int:
        with self._cond:
            i = self._next
            np.copyto(self._buf[i], bgr)
            self._latest += 1
            self._seq[i] = self._latest
            self._next = (i + 1) % len(self._buf)
            self._cond.notify_all()
            return self._latest

    def read_latest(self, after: int = -1, timeout: float = 1.0) -> tuple[int, np.ndarray | None]:
        """after보다 새 프레임이 올 때까지 기다렸다가 (seq, 복사본)을 돌려준다."""
        with self._cond:
            if not self._cond.wait_for(lambda: self._latest > after, timeout):
                return after, None
            i = (self._next - 1) % len(self._buf)
            return int(self._seq[i]), self._buf[i].copy()

    def read_latest_resized(self, scale: float, after: int = -1,
                            timeout: float = 1.0) -> tuple[int, np.ndarray | None]:
        """원본 전체를 복사하지 않고 슬롯에서 바로 축소본을 만든다 (송출용)."""
        with self._cond:
            if not self._cond.wait_for(lambda: self._latest > after, timeout):
                return after, None
            i = (self._next - 1) % len(self._buf)
            src = self._buf[i]
            img = src.copy() if scale >= 1 else cv2.resize(src, None, fx=scale, fy=scale,
                                                           interpolation=cv2.INTER_AREA)
            return int(self._seq[i]), img

    def wipe(self) -> None:
        with self._lock:
            self._buf.fill(0)
