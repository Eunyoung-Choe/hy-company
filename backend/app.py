"""
토큰 최적화 영상 요약 API (Flask · Google Colab + ngrok)

  1단계  OpenCV   : 1fps 샘플링 + 픽셀 변화(absdiff)로 정지 프레임 드롭        (CPU, 초경량)
  2단계  DINOv2   : ViT-S/14(dinov2_vits14 = facebook/dinov2-small) 코사인 유사도로 장면 전환만 키프레임
  3단계  캡션     : 키프레임만 저해상도로 VLM에 넣어 1줄 캡션
  4단계  요약     : 시간순 캡션 텍스트만으로 최종 요약 (이미지 재전송 없음)

  3·4단계 엔진 (업로드마다 form 필드 "engine"으로 선택, 기본값은 CAPTION_BACKEND)
    local  (기본) Qwen2.5-VL-3B-Instruct를 Colab GPU에서 직접 실행 → API 키·비용 없음
    openai        OpenAI API (OPENAI_MODEL, 기본 gpt-5.4-mini · OPENAI_API_KEY가 있을 때만 사용 가능)

API
  GET  /                 상태 확인
  POST /api/upload       form-data "video"(MP4) → {"job_id"}
  GET  /api/jobs/<id>    진행 상황 · 결과

비밀값은 환경변수로만 받습니다 (Colab Secrets 또는 로컬 .env). 코드에 키를 적지 마세요.
  NGROK_AUTHTOKEN  있으면 ngrok 터널을 열어 외부 URL 발급
  NGROK_DOMAIN     선택 · ngrok 무료 고정 도메인(xxx.ngrok-free.dev) → 매번 같은 URL
  OPENAI_API_KEY   선택 · 있으면 화면에서 GPT 엔진을 고를 수 있음
"""
from __future__ import annotations

import base64
import logging
import math
import os
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from PIL import Image
from transformers import AutoModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))  # 로컬 개발용. Colab에서는 노트북이 Secrets를 환경변수로 넣어 줌


def env_float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def env_int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


# ───────────────────────── 설정값 (환경변수로 덮어쓰기 가능) ─────────────────────────
SAMPLE_FPS = env_float("SAMPLE_FPS", 1.0)                      # 1단계 샘플링 fps
PIXEL_DIFF_THRESHOLD = env_float("PIXEL_DIFF_THRESHOLD", 6.0)  # 1단계: 평균 픽셀 차(0~255) 미만이면 드롭
DINO_MODEL_ID = os.getenv("DINO_MODEL_ID", "facebook/dinov2-small")
DINO_SIM_THRESHOLD = env_float("DINO_SIM_THRESHOLD", 0.85)     # 2단계: 코사인 유사도 미만이면 키프레임
DINO_BATCH = env_int("DINO_BATCH", 16)
MAX_KEYFRAMES = env_int("MAX_KEYFRAMES", 24)                   # 캡션 호출 수 상한
CAPTION_MAX_SIDE = env_int("CAPTION_MAX_SIDE", 512)            # 3단계 이미지 긴 변(px)
CAPTION_BACKEND = os.getenv("CAPTION_BACKEND", "local").strip().lower()   # local | openai
# local (Qwen2.5-VL)
LOCAL_VLM_ID = os.getenv("LOCAL_VLM_ID", "Qwen/Qwen2.5-VL-3B-Instruct")
VLM_MAX_PIXELS = env_int("VLM_MAX_PIXELS", 448 * 448)          # 이미지 토큰 상한 (448² ≈ 256토큰)
VLM_MIN_PIXELS = env_int("VLM_MIN_PIXELS", 224 * 224)
VLM_DTYPE = os.getenv("VLM_DTYPE", "auto").strip().lower()     # auto | float16 | bfloat16 | float32
# openai
CAPTION_WORKERS = env_int("CAPTION_WORKERS", 4)
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "none").strip().lower()  # 안 받으면 자동 재시도
# 비용 환산용 단가(USD / 1M 토큰). local이면 실제 청구는 0원이고, 'API로 처리했다면' 환산에만 씀
PRICE_INPUT_PER_1M = env_float("PRICE_INPUT_PER_1M", 0.25)
PRICE_OUTPUT_PER_1M = env_float("PRICE_OUTPUT_PER_1M", 2.00)
BASELINE_FPS = env_float("BASELINE_FPS", 1.0)                  # '영상 통째로' 가정 시 프레임 기준
MAX_UPLOAD_MB = env_int("MAX_UPLOAD_MB", 200)
MAX_VIDEO_SECONDS = env_int("MAX_VIDEO_SECONDS", 600)          # 공개 API 남용 방지
JOB_TTL_SECONDS = env_int("JOB_TTL_SECONDS", 3600)
ALLOWED_ORIGINS = [o.strip() for o in os.getenv(
    "ALLOWED_ORIGINS", "https://hy-company-ten.vercel.app,http://localhost:3000").split(",") if o.strip()]
PORT = env_int("PORT", 5000)                                   # ngrok이 이 포트를 외부로 연결

CAPTION_PROMPT = "이 상황을 1줄로 묘사해 줘."
SYSTEM_PROMPT = "너는 영상 장면을 설명하는 도우미야. 항상 자연스러운 한국어로만 간결하게 답해."
SUMMARY_PROMPT = "다음은 영상의 시간대별 핵심 장면을 설명한 텍스트야. 이를 바탕으로 영상 전체 내용을 자연스러운 하나의 글로 요약해 줘."

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("pipeline")

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
torch.set_num_threads(max(1, os.cpu_count() or 1))
IMAGENET_MEAN = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
IMAGENET_STD = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)


@dataclass
class Frame:
    t: float            # 영상 내 시각(초)
    image: np.ndarray   # BGR, 긴 변 640px로 축소 보관 (메모리 절약)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    reasoning_tokens: int = 0   # 출력 토큰 중 보이지 않는 추론 토큰 (OpenAI 추론 모델)

    def add(self, u) -> None:   # OpenAI 응답의 usage
        if u is None:
            return
        self.add_counts(u.prompt_tokens or 0, u.completion_tokens or 0)
        details = getattr(u, "completion_tokens_details", None)
        self.reasoning_tokens += (getattr(details, "reasoning_tokens", 0) or 0) if details else 0

    def add_counts(self, n_in: int, n_out: int) -> None:
        self.input_tokens += n_in
        self.output_tokens += n_out
        self.calls += 1


# ───────────────────────── 작업 상태 (프론트 폴링용) ─────────────────────────
STAGES = {1: "OpenCV 필터링 중", 2: "DINO 분석 중", 3: "캡션 생성 중", 4: "최종 요약 중"}
STAGE_SPAN = {1: (0, 25), 2: (25, 50), 3: (50, 85), 4: (85, 100)}
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
WORKER_SLOT = threading.Semaphore(1)   # 무료 CPU: 한 번에 한 영상만 처리


def update_job(job_id: str, **fields) -> None:
    with JOBS_LOCK:
        JOBS[job_id].update(fields, updated_at=time.time())


def set_progress(job_id: str, stage: int, fraction: float, message: str = "") -> None:
    lo, hi = STAGE_SPAN[stage]
    fraction = max(0.0, min(1.0, fraction))
    update_job(job_id, stage=stage, stage_label=STAGES[stage],
               percent=round(lo + (hi - lo) * fraction, 1), message=message)


def purge_old_jobs() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    with JOBS_LOCK:
        for jid in [j for j, v in JOBS.items() if v["updated_at"] < cutoff and v["status"] in ("done", "error")]:
            del JOBS[jid]


# ───────────────────────── 공통 유틸 ─────────────────────────
def resize_max(img: np.ndarray, max_side: int) -> np.ndarray:
    h, w = img.shape[:2]
    scale = max_side / max(h, w)
    if scale >= 1:
        return img
    return cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)


def jpeg_b64(img: np.ndarray, max_side: int, quality: int = 80) -> str:
    ok, buf = cv2.imencode(".jpg", resize_max(img, max_side), [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG 인코딩 실패")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def fmt_time(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    return f"{m:02d}:{s:02d}"


# ───────────────────────── 1단계: OpenCV 1차 필터 ─────────────────────────
def stage1_opencv(path: str, job_id: str) -> tuple[list[Frame], dict]:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError("영상을 열 수 없습니다. MP4(H.264) 파일인지 확인해 주세요.")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if total and total / fps > MAX_VIDEO_SECONDS:
        cap.release()
        raise RuntimeError(f"영상이 너무 깁니다 ({total / fps:.0f}초). 최대 {MAX_VIDEO_SECONDS}초까지 처리합니다.")
    step = max(1, round(fps / SAMPLE_FPS))

    kept: list[Frame] = []
    ref_small = None   # 마지막으로 '통과한' 프레임과 비교 → 천천히 변하는 장면도 누적 변화로 잡음
    sampled = 0
    idx = 0
    while cap.grab():  # grab은 디코딩만, 필요한 프레임만 retrieve
        if idx % step == 0:
            ok, frame = cap.retrieve()
            if ok:
                sampled += 1
                small = cv2.GaussianBlur(cv2.cvtColor(resize_max(frame, 160), cv2.COLOR_BGR2GRAY), (5, 5), 0)
                diff = None if ref_small is None else float(cv2.absdiff(small, ref_small).mean())
                if diff is None or diff >= PIXEL_DIFF_THRESHOLD:
                    kept.append(Frame(t=idx / fps, image=resize_max(frame, 640)))
                    ref_small = small
                if total and sampled % 5 == 0:
                    set_progress(job_id, 1, idx / total, f"샘플 {sampled}장 중 {len(kept)}장 통과")
        idx += 1
        if idx / fps > MAX_VIDEO_SECONDS:   # 프레임 수 메타데이터가 없는 파일 대비
            break
    cap.release()

    duration = idx / fps if fps else 0.0
    if sampled == 0:
        raise RuntimeError("영상에서 프레임을 읽지 못했습니다.")
    log.info("[OpenCV] %.1fs 영상 · 1fps 샘플 %d장 → 정지 프레임 드롭 후 %d장 (threshold=%.1f)",
             duration, sampled, len(kept), PIXEL_DIFF_THRESHOLD)
    set_progress(job_id, 1, 1.0, f"샘플 {sampled}장 중 {len(kept)}장 통과")
    return kept, {"fps": fps, "width": width, "height": height, "duration": duration,
                  "sampled": sampled, "stage1_kept": len(kept)}


# ───────────────────────── 2단계: DINOv2 2차 필터 ─────────────────────────
_dino = None
_dino_lock = threading.Lock()


def get_dino():
    global _dino
    with _dino_lock:
        if _dino is None:
            log.info("[DINO] %s 로드 · device=%s", DINO_MODEL_ID, DEVICE)
            _dino = AutoModel.from_pretrained(DINO_MODEL_ID).eval().to(DEVICE)
    return _dino


def to_tensor(bgr: np.ndarray) -> torch.Tensor:
    rgb = cv2.cvtColor(cv2.resize(bgr, (224, 224), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
    x = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
    return (x - IMAGENET_MEAN) / IMAGENET_STD


@torch.inference_mode()
def stage2_dino(frames: list[Frame], job_id: str) -> list[Frame]:
    if not frames:
        return []
    set_progress(job_id, 2, 0.0, "DINOv2 모델 준비 중")
    model = get_dino()

    embs = []
    for i in range(0, len(frames), DINO_BATCH):
        batch = torch.stack([to_tensor(f.image) for f in frames[i:i + DINO_BATCH]]).to(DEVICE)
        cls = model(pixel_values=batch).pooler_output          # 정규화된 CLS 토큰 (384차원)
        embs.append(F.normalize(cls.float(), dim=-1).cpu())
        n = min(i + DINO_BATCH, len(frames))
        set_progress(job_id, 2, n / len(frames) * 0.9, f"특징 추출 {n}/{len(frames)}")
    emb = torch.cat(embs)

    # 직전 프레임(sim_prev)과 마지막 키프레임(sim_key) 유사도를 모두 로깅.
    # 판정은 sim_key 기준: 천천히 변하는 장면이 키프레임을 연달아 만들지 않게 함.
    keys = [0]
    log.info("[DINO] threshold=%.2f ─────────────────────────────────────────", DINO_SIM_THRESHOLD)
    log.info("[DINO] %5s │ %6s │ %8s │ %8s │ %s", "#", "time", "sim_prev", "sim_key", "결과")
    log.info("[DINO] %5d │ %6s │ %8s │ %8s │ ★ KEYFRAME (첫 장면)", 0, fmt_time(frames[0].t), "-", "-")
    for i in range(1, len(frames)):
        sim_prev = float(emb[i] @ emb[i - 1])
        sim_key = float(emb[i] @ emb[keys[-1]])
        is_key = sim_key < DINO_SIM_THRESHOLD
        if is_key:
            keys.append(i)
        log.info("[DINO] %5d │ %6s │ %8.3f │ %8.3f │ %s", i, fmt_time(frames[i].t), sim_prev, sim_key,
                 "★ KEYFRAME" if is_key else "skip")

    if len(keys) > MAX_KEYFRAMES:  # 비용 상한: 시간 축에서 고르게 줄임
        pick = np.linspace(0, len(keys) - 1, MAX_KEYFRAMES).round().astype(int)
        log.info("[DINO] 키프레임 %d장 → 상한 %d장으로 균등 축소", len(keys), MAX_KEYFRAMES)
        keys = [keys[j] for j in sorted(set(pick.tolist()))]

    log.info("[DINO] %d장 중 키프레임 %d장 선택", len(frames), len(keys))
    set_progress(job_id, 2, 1.0, f"키프레임 {len(keys)}장 선택")
    return [frames[k] for k in keys]


# ───────────────────────── 3·4단계 엔진 A: 로컬 Qwen2.5-VL ─────────────────────────
_vlm = None
_vlm_lock = threading.Lock()


def vlm_dtype() -> torch.dtype:
    if DEVICE != "cuda":
        return torch.float32
    if VLM_DTYPE in ("float16", "bfloat16", "float32"):
        return getattr(torch, VLM_DTYPE)
    # auto: Qwen2.5-VL은 fp16에서 값이 넘쳐 '!!!!'만 출력하는 경우가 있음 → 가능하면 bf16.
    #   A100·L4 등(compute 8.0+)은 bf16 네이티브, T4는 PyTorch가 bf16을 에뮬레이션(조금 느리지만 안전)
    if torch.cuda.get_device_capability()[0] >= 8 or torch.cuda.is_bf16_supported():
        return torch.bfloat16
    return torch.float16


def get_vlm():
    global _vlm
    with _vlm_lock:
        if _vlm is None:
            from transformers import AutoProcessor
            try:
                from transformers import Qwen2_5_VLForConditionalGeneration as VLM
            except ImportError:  # 클래스명이 바뀐 버전 대비
                from transformers import AutoModelForImageTextToText as VLM
            dtype = vlm_dtype()
            log.info("[VLM] %s 로드 중 (첫 실행 시 약 7GB 다운로드) · device=%s · dtype=%s", LOCAL_VLM_ID, DEVICE, dtype)
            if DEVICE != "cuda":
                log.warning("[VLM] GPU가 없습니다. CPU로는 캡션 1장에 수 분이 걸릴 수 있어요 (Colab: 런타임 → T4 GPU)")
            processor = AutoProcessor.from_pretrained(LOCAL_VLM_ID, min_pixels=VLM_MIN_PIXELS, max_pixels=VLM_MAX_PIXELS)
            model = VLM.from_pretrained(LOCAL_VLM_ID, torch_dtype=dtype).eval().to(DEVICE)
            _vlm = (processor, model)
            log.info("[VLM] 준비 완료")
    return _vlm


@torch.inference_mode()
def vlm_generate(prompt: str, image: Image.Image | None, max_new_tokens: int) -> tuple[str, int, int, int]:
    """(응답, 입력 토큰, 출력 토큰, 이미지 토큰) — 토큰은 모델 입력에서 실제로 센 값."""
    processor, model = get_vlm()
    user = ([{"type": "image"}] if image is not None else []) + [{"type": "text", "text": prompt}]
    messages = [{"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
                {"role": "user", "content": user}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=[image] if image is not None else None, return_tensors="pt").to(DEVICE)
    out = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False, repetition_penalty=1.05)
    n_in = int(inputs["input_ids"].shape[1])
    new_tokens = out[:, n_in:]
    answer = processor.batch_decode(new_tokens, skip_special_tokens=True)[0].strip()
    img_tokens = 0
    if "image_grid_thw" in inputs:   # Qwen: (t·h·w 패치) / merge_size² = LLM에 들어간 이미지 토큰
        merge = getattr(processor.image_processor, "merge_size", 2)
        img_tokens = int(inputs["image_grid_thw"].prod(-1).sum()) // (merge * merge)
    return answer, n_in, int(new_tokens.shape[1]), img_tokens


CAPTION_FAILED = "(이 장면은 캡션 생성에 실패했어요)"


def looks_broken(text: str) -> bool:
    """수치 넘침(fp16 overflow) 때 나오는 '!!!!' 같은 무의미한 출력 감지."""
    s = "".join(text.split())
    return not s or (len(s) >= 3 and s.count("!") / len(s) > 0.5)


def local_captions(keyframes: list[Frame], job_id: str, usage: Usage) -> tuple[list[dict], list[int]]:
    set_progress(job_id, 3, 0.0, "Qwen2.5-VL 모델 준비 중")
    get_vlm()
    results, image_tokens = [], []
    for i, f in enumerate(keyframes):
        text = ""
        for side in (CAPTION_MAX_SIDE, 336):   # 깨지면 해상도를 바꿔 한 번 재시도
            rgb = cv2.cvtColor(resize_max(f.image, side), cv2.COLOR_BGR2RGB)
            text, n_in, n_out, n_img = vlm_generate(CAPTION_PROMPT, Image.fromarray(rgb), max_new_tokens=64)
            usage.add_counts(n_in, n_out)   # 재시도 토큰도 실제 사용량에 포함
            if side == CAPTION_MAX_SIDE:
                image_tokens.append(n_img)
            log.info("[CAPTION] %s (side=%d, in=%d, img=%d, out=%d) %s", fmt_time(f.t), side, n_in, n_img, n_out, text)
            if not looks_broken(text):
                break
            log.warning("[CAPTION] %s 깨진 출력 감지 → %s", fmt_time(f.t), "336px로 재시도" if side != 336 else "실패 처리")
        failed = looks_broken(text)
        results.append(keyframe_entry(f, CAPTION_FAILED if failed else text, failed))
        set_progress(job_id, 3, (i + 1) / len(keyframes), f"캡션 {i + 1}/{len(keyframes)}")
    return results, image_tokens


def local_summary(prompt: str, usage: Usage) -> tuple[str, int]:
    text, n_in, n_out, _ = vlm_generate(prompt, None, max_new_tokens=512)   # 이미지 없이 텍스트만
    usage.add_counts(n_in, n_out)
    if looks_broken(text):   # 숨기지 않고 오류로 알림
        raise RuntimeError("요약 출력이 깨졌습니다(수치 넘침). Colab Secrets에 VLM_DTYPE=float32를 넣고 다시 실행해 보세요.")
    return text, n_out


# ───────────────────────── 3·4단계 엔진 B: OpenAI (선택) ─────────────────────────
def openai_client():
    from openai import OpenAI
    return OpenAI()   # OPENAI_API_KEY 환경변수 사용


_effort_ok: dict[str, str | None] = {}   # 모델별로 통과한 reasoning_effort 값 (None = 보내지 않음)


def effort_candidates(name: str) -> list[str | None]:
    """추론 모델(gpt-5*, o*)은 추론 토큰을 줄이는 값부터 시도. 모델마다 허용 값이 달라 순서대로 재시도."""
    n = name.lower()
    if not (n.startswith("gpt-5") or (n.startswith("o") and n[1:2].isdigit())):
        return [None]   # 일반 모델(gpt-4.1-mini 등)은 이 옵션을 받지 않음
    out: list[str | None] = []
    for v in (OPENAI_REASONING_EFFORT, "none", "minimal", "low", None):
        if v not in out:
            out.append(v)
    return out


def openai_chat(client, **kwargs):
    from openai import BadRequestError

    candidates = [_effort_ok[OPENAI_MODEL]] if OPENAI_MODEL in _effort_ok else effort_candidates(OPENAI_MODEL)
    last: Exception | None = None
    for effort in candidates:
        try:
            r = client.chat.completions.create(
                model=OPENAI_MODEL, **({"reasoning_effort": effort} if effort else {}), **kwargs)
            _effort_ok[OPENAI_MODEL] = effort
            return r
        except BadRequestError as e:
            if "reasoning" not in str(e).lower():
                raise   # 권한·형식 오류 등은 숨기지 않음
            last = e
            log.info("[OpenAI] %s는 reasoning_effort=%s를 받지 않음 → 다음 값으로 재시도", OPENAI_MODEL, effort)
    raise last  # type: ignore[misc]


def openai_caption_one(client, b64: str):
    r = openai_chat(
        client,
        max_completion_tokens=800,   # 추론 토큰 포함 상한. 실제로 쓴 만큼만 과금
        messages=[{"role": "user", "content": [
            {"type": "text", "text": CAPTION_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"}},
        ]}],
    )
    return (r.choices[0].message.content or "").strip(), r.usage


def openai_captions(keyframes: list[Frame], job_id: str, usage: Usage) -> list[dict]:
    client = openai_client()
    images = [jpeg_b64(f.image, CAPTION_MAX_SIDE) for f in keyframes]
    results: list[dict] = [{} for _ in keyframes]
    set_progress(job_id, 3, 0.0, f"캡션 0/{len(keyframes)}")
    with ThreadPoolExecutor(max_workers=CAPTION_WORKERS) as pool:
        futures = [pool.submit(openai_caption_one, client, b64) for b64 in images]
        for i, fut in enumerate(futures):
            text, u = fut.result()   # API 오류는 그대로 올려 작업을 '오류'로 표시 (숨기지 않음)
            usage.add(u)
            results[i] = keyframe_entry(keyframes[i], text)
            log.info("[CAPTION] %s %s", fmt_time(keyframes[i].t), text)
            set_progress(job_id, 3, (i + 1) / len(keyframes), f"캡션 {i + 1}/{len(keyframes)}")
    return results


def openai_summary(prompt: str, usage: Usage) -> tuple[str, int]:
    r = openai_chat(
        openai_client(),
        max_completion_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    usage.add(r.usage)
    return (r.choices[0].message.content or "").strip(), (r.usage.completion_tokens if r.usage else 0)


# ───────────────────────── 3단계 · 4단계 ─────────────────────────
def keyframe_entry(f: Frame, caption: str, failed: bool = False) -> dict:
    return {"time": round(f.t, 1), "time_label": fmt_time(f.t), "failed": failed or not caption,
            "image": jpeg_b64(f.image, CAPTION_MAX_SIDE), "caption": caption or "(캡션이 비어 있음)"}


def available_engines() -> list[str]:
    engines = ["local"] if CAPTION_BACKEND == "local" else []   # openai 전용으로 켜면 Qwen을 로드하지 않음
    if os.getenv("OPENAI_API_KEY"):
        engines.append("openai")
    return engines


def stage3_captions(keyframes: list[Frame], job_id: str, usage: Usage, engine: str) -> tuple[list[dict], list[int]]:
    if engine == "openai":
        return openai_captions(keyframes, job_id, usage), []
    return local_captions(keyframes, job_id, usage)


def stage4_summary(captions: list[dict], job_id: str, usage: Usage, engine: str) -> tuple[str, int]:
    set_progress(job_id, 4, 0.1, "캡션 텍스트로 요약 중 (이미지 미전송)")
    usable = [c for c in captions if not c["failed"]]   # 실패한 캡션은 요약 입력에서 제외
    if not usable:
        raise RuntimeError("모든 장면의 캡션 생성에 실패했습니다. Colab 로그의 [CAPTION] 줄을 확인해 주세요.")
    timeline = "\n".join(f"[{c['time_label']}] {c['caption']}" for c in usable)   # 텍스트만!
    prompt = f"{SUMMARY_PROMPT}\n\n{timeline}"
    summary, out_tokens = (openai_summary if engine == "openai" else local_summary)(prompt, usage)
    set_progress(job_id, 4, 1.0, "완료")
    return summary, out_tokens


# ───────────────────────── 토큰 지표 ─────────────────────────
def image_tokens_high(w: float, h: float) -> int:
    """detail=high 타일 방식 이미지 토큰 추정: 2048 박스 → 짧은 변 768 → 512px 타일당 170 + 85."""
    if w <= 0 or h <= 0:
        return 0
    s = min(1.0, 2048 / max(w, h)); w, h = w * s, h * s
    s = min(1.0, 768 / min(w, h)); w, h = w * s, h * s
    return 85 + 170 * math.ceil(w / 512) * math.ceil(h / 512)


def cost(inp: int, out: int) -> float:
    return inp / 1e6 * PRICE_INPUT_PER_1M + out / 1e6 * PRICE_OUTPUT_PER_1M


def build_metrics(stats: dict, usage: Usage, summary_out_tokens: int, image_tokens: list[int], engine: str) -> dict:
    """'영상 통째로' 기준선은 같은 엔진의 토큰 계산 방식으로 잡아 사과-사과 비교."""
    baseline_frames = max(1, math.ceil(stats["duration"] * BASELINE_FPS))
    local = engine != "openai"
    if local and image_tokens:
        per_frame = round(sum(image_tokens) / len(image_tokens))   # Qwen에 실제 들어간 프레임당 이미지 토큰
        basis = f"모든 {BASELINE_FPS:g}fps 프레임을 같은 해상도로 Qwen2.5-VL에 넣었다고 가정"
    else:
        per_frame = image_tokens_high(stats["width"], stats["height"])
        basis = f"모든 {BASELINE_FPS:g}fps 프레임을 detail=high로 {OPENAI_MODEL}에 보냈다고 가정"
    baseline_in = baseline_frames * per_frame + 100       # +100: 프롬프트 텍스트 대략치
    baseline_out = summary_out_tokens                      # 같은 길이 요약을 출력한다고 가정
    actual = usage.input_tokens + usage.output_tokens
    baseline = baseline_in + baseline_out
    actual_cost, baseline_cost = cost(usage.input_tokens, usage.output_tokens), cost(baseline_in, baseline_out)
    return {
        "backend": "local" if local else "openai",
        "engine": LOCAL_VLM_ID if local else OPENAI_MODEL,
        "billed_cost_usd": 0.0 if local else actual_cost,   # 실제 청구액 (로컬 모델은 0, API는 설정 단가 기준)
        "reasoning_tokens": usage.reasoning_tokens,
        "actual_tokens": actual,
        "actual_input_tokens": usage.input_tokens,
        "actual_output_tokens": usage.output_tokens,
        "api_calls": usage.calls,
        "baseline_tokens": baseline,
        "baseline_frames": baseline_frames,
        "baseline_tokens_per_frame": per_frame,
        "saved_tokens": baseline - actual,
        "saved_percent": round((baseline - actual) / baseline * 100, 1) if baseline else 0.0,
        "actual_cost_usd": actual_cost,
        "baseline_cost_usd": baseline_cost,
        "saved_cost_usd": baseline_cost - actual_cost,
        "assumption": f"예상치: {basis}. 비용은 API 단가(입력 ${PRICE_INPUT_PER_1M}/1M · "
                      f"출력 ${PRICE_OUTPUT_PER_1M}/1M)로 환산" + (" — 로컬 모델이라 실제 청구는 $0" if local else ""),
    }


# ───────────────────────── 파이프라인 실행 (백그라운드 스레드) ─────────────────────────
def run_pipeline(job_id: str, path: str, engine: str) -> None:
    started = time.time()
    try:
        update_job(job_id, status="running")
        usage = Usage()
        log.info("[JOB] %s 시작 · 캡션·요약 엔진=%s", job_id, LOCAL_VLM_ID if engine == "local" else OPENAI_MODEL)

        frames, stats = stage1_opencv(path, job_id)
        keyframes = stage2_dino(frames, job_id)
        if not keyframes:
            raise RuntimeError("키프레임을 찾지 못했습니다.")
        captions, image_tokens = stage3_captions(keyframes, job_id, usage, engine)
        summary, summary_out = stage4_summary(captions, job_id, usage, engine)

        stats["keyframes"] = len(keyframes)
        update_job(job_id, status="done", percent=100, result={
            "summary": summary,
            "keyframes": captions,
            "funnel": stats,
            "metrics": build_metrics(stats, usage, summary_out, image_tokens, engine),
            "elapsed_sec": round(time.time() - started, 1),
        })
        log.info("[DONE] %s · %s · %.1fs · 입력 %d · 출력 %d (추론 %d)", job_id, engine, time.time() - started,
                 usage.input_tokens, usage.output_tokens, usage.reasoning_tokens)
    except Exception as e:  # 오류는 프론트에 그대로 전달
        log.exception("[ERROR] %s", job_id)
        update_job(job_id, status="error", error=str(e))
    finally:
        WORKER_SLOT.release()
        try:
            os.remove(path)
        except OSError:
            pass


# ───────────────────────── Flask ─────────────────────────
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
CORS(app, resources={r"/api/*": {"origins": ALLOWED_ORIGINS}})
UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "video-summarizer")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/")
@app.get("/api/health")
def health():
    engines = available_engines()
    return jsonify(status="ok", default_engine=CAPTION_BACKEND, engines=engines,
                   engine_models={"local": LOCAL_VLM_ID, "openai": OPENAI_MODEL},
                   dino=DINO_MODEL_ID, device=DEVICE,
                   models_ready=_dino is not None and (_vlm is not None or "local" not in engines),
                   warmup_error=WARMUP_ERROR, busy=WORKER_SLOT._value == 0)  # noqa: SLF001


@app.post("/api/upload")
def upload():
    engines = available_engines()
    engine = (request.form.get("engine") or CAPTION_BACKEND).strip().lower()
    if engine not in engines:
        hint = " (Colab Secrets에 OPENAI_API_KEY를 넣고 다시 실행)" if engine == "openai" else ""
        return jsonify(error=f"'{engine}' 엔진을 사용할 수 없습니다. 사용 가능: {', '.join(engines) or '없음'}{hint}"), 400
    f = request.files.get("video")
    if f is None or not f.filename:
        return jsonify(error="MP4 파일을 선택해 주세요."), 400
    if not f.filename.lower().endswith(".mp4"):
        return jsonify(error="MP4 파일만 업로드할 수 있습니다."), 400
    if not WORKER_SLOT.acquire(blocking=False):
        return jsonify(error="다른 영상을 처리 중입니다. 잠시 후 다시 시도해 주세요."), 429

    purge_old_jobs()
    job_id = uuid.uuid4().hex[:12]
    path = os.path.join(UPLOAD_DIR, f"{job_id}.mp4")   # 사용자 파일명은 경로에 쓰지 않음
    try:
        f.save(path)
    except Exception:
        WORKER_SLOT.release()
        raise
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "queued", "stage": 1, "stage_label": STAGES[1], "percent": 0,
                        "message": "대기 중", "result": None, "error": None, "updated_at": time.time()}
    threading.Thread(target=run_pipeline, args=(job_id, path, engine), daemon=True).start()
    return jsonify(job_id=job_id)


@app.get("/api/jobs/<job_id>")
def job_status(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return jsonify(error="작업을 찾을 수 없습니다. 서버가 재시작되었을 수 있어요."), 404
        return jsonify({k: v for k, v in job.items() if k != "updated_at"})


@app.errorhandler(413)
def too_large(_):
    return jsonify(error=f"파일이 너무 큽니다 (최대 {MAX_UPLOAD_MB}MB)."), 413


# ───────────────────────── ngrok: 외부 인터넷 연결 ─────────────────────────
def start_ngrok(port: int) -> str | None:
    """NGROK_AUTHTOKEN이 있으면 터널을 열고 공개 URL을 반환. 없으면 로컬 전용으로 실행."""
    token = os.getenv("NGROK_AUTHTOKEN")
    if not token:
        log.info("[ngrok] NGROK_AUTHTOKEN 없음 → 외부 URL 없이 http://localhost:%d 에서만 실행", port)
        return None
    from pyngrok import ngrok
    from pyngrok.exception import PyngrokNgrokError

    try:
        ngrok.set_auth_token(token)
    except PyngrokNgrokError as e:
        # Colab에서 재실행하면 ngrok.yml에 토큰이 이미 저장돼 있어 이 오류가 남 → 무시하고 진행
        if "already set" not in str(e).lower():
            raise   # 그 밖의 오류(잘못된 토큰 등)는 숨기지 않음
        log.info("[ngrok] 토큰이 이미 설정되어 있어 그대로 사용합니다.")
    domain = os.getenv("NGROK_DOMAIN", "").strip().removeprefix("https://").rstrip("/")
    if not domain:
        tunnel = ngrok.connect(port, "http")
    else:
        try:
            tunnel = ngrok.connect(port, "http", domain=domain)        # 구버전 ngrok 에이전트
        except PyngrokNgrokError as e:
            detail = f"{e} {getattr(e, 'body', '')}"
            if "field domain not found" not in detail:
                raise
            # 최신 ngrok 에이전트는 고정 도메인을 'url' 항목으로 받음
            log.info("[ngrok] 최신 에이전트 형식(url)으로 고정 도메인 재시도")
            tunnel = ngrok.connect(port, "http", url=f"https://{domain}")
    url = tunnel.public_url.replace("http://", "https://", 1)
    line = "═" * 64
    print(f"\n{line}\n  🌐 공개 API URL : {url}\n"
          f"  → Next.js의 NEXT_PUBLIC_API_URL 에 이 주소를 넣으세요 (끝에 / 없이)\n"
          f"  → 상태 확인    : {url}/api/health\n"
          f"  {'(고정 도메인)' if domain else '⚠ 무료 임시 주소: 실행할 때마다 바뀝니다. NGROK_DOMAIN 사용 권장'}\n{line}\n",
          flush=True)
    return url


WARMUP_ERROR: str | None = None


def warmup() -> None:
    """서버 시작 직후 모델을 미리 로드 → 첫 업로드 사용자가 다운로드를 기다리지 않게."""
    global WARMUP_ERROR
    try:
        get_dino()
        if CAPTION_BACKEND != "openai":
            get_vlm()
    except Exception as e:  # 실패해도 서버는 유지, 업로드 시 다시 시도하고 오류는 /api/health에 표시
        WARMUP_ERROR = str(e)
        log.exception("[WARMUP] 모델 미리 로드 실패")


if __name__ == "__main__":
    if CAPTION_BACKEND not in ("local", "openai"):
        raise SystemExit(f"CAPTION_BACKEND는 local 또는 openai여야 합니다 (현재: {CAPTION_BACKEND})")
    log.info("device=%s · 기본 엔진=%s · 사용 가능=%s (openai 모델=%s) · origins=%s · port=%d",
             DEVICE, CAPTION_BACKEND, available_engines(), OPENAI_MODEL, ALLOWED_ORIGINS, PORT)
    threading.Thread(target=warmup, daemon=True).start()
    start_ngrok(PORT)
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True, use_reloader=False)
