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
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if gray.shape != (kh, kw):
        gray = cv2.resize(gray, (kw, kh), interpolation=cv2.INTER_AREA)
    regions = _regions(gray, v.ref_key, frame.shape[1] / kw)  # 마스킹 전 픽셀로 변경 영역 계산
    full_w = kw / DIFF_SCALE
    black_boxes(frame, scale_hits(v.hits, frame.shape[1] / full_w))
    held = v.masked_frame
    for x, y, w, h in regions:
        if held is not None and held.shape == frame.shape:
            # 검사 중인 영역은 직전 검증본(이미 마스킹됨)으로 덮어 '잠깐 멈춘' 것처럼 보이게
            frame[y:y + h, x:x + w] = held[y:y + h, x:x + w]
        else:
            mosaic(frame, x, y, w, h)  # 검증본이 없을 때만 예전처럼 모자이크
    return frame, len(regions)
