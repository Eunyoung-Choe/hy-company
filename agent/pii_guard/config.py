from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_env_file(path: Path) -> None:
    """agent/.env 를 읽어 os.environ에 채운다 (이미 설정된 값은 유지)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _region(raw: str) -> tuple[int, int, int, int] | None:
    if not raw:
        return None
    parts = [int(p) for p in raw.replace(" ", "").split(",")]
    if len(parts) != 4:
        raise ValueError("CAPTURE_REGION 형식: left,top,width,height")
    return parts[0], parts[1], parts[2], parts[3]


@dataclass(frozen=True)
class Config:
    monitor: int
    region: tuple[int, int, int, int] | None
    fps: int
    capture_backend: str
    ring_slots: int
    ocr_gpu: bool
    ocr_langs: list[str]
    ocr_scale: float
    ocr_threads: int
    stream_host: str
    stream_port: int
    jpeg_quality: int
    stream_scale: float
    allowed_origins: list[str]
    supabase_url: str
    supabase_key: str
    audit_bucket: str
    audit_interval: float
    session_id: str

    @staticmethod
    def from_env() -> "Config":
        e = os.environ.get
        return Config(
            monitor=int(e("CAPTURE_MONITOR", "1")),
            region=_region(e("CAPTURE_REGION", "")),
            fps=int(e("CAPTURE_FPS", "60")),
            capture_backend=e("CAPTURE_BACKEND", "auto").lower(),
            ring_slots=int(e("RING_SLOTS", "4")),
            ocr_gpu=e("OCR_GPU", "auto").lower() != "false",
            ocr_langs=[s.strip() for s in e("OCR_LANGS", "ko,en").split(",") if s.strip()],
            ocr_scale=float(e("OCR_SCALE", "0.5")),
            ocr_threads=int(e("OCR_THREADS") or max(1, (os.cpu_count() or 4) - 4)),
            stream_host=e("STREAM_HOST", "127.0.0.1"),
            stream_port=int(e("STREAM_PORT", "8765")),
            jpeg_quality=int(e("JPEG_QUALITY", "80")),
            stream_scale=float(e("STREAM_SCALE", "0.5")),
            allowed_origins=[o.strip().rstrip("/") for o in
                             e("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()],
            supabase_url=e("SUPABASE_URL", "").rstrip("/"),
            supabase_key=e("SUPABASE_SECRET_KEY", ""),
            audit_bucket=e("AUDIT_BUCKET", "pii-audit"),
            audit_interval=float(e("AUDIT_INTERVAL_SEC", "10")),
            session_id=e("SESSION_ID", os.environ.get("COMPUTERNAME", "agent")).lower(),
        )
