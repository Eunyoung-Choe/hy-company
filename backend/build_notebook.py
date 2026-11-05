"""app.py를 담은 Colab 실행 노트북(colab_backend.ipynb)을 만듭니다.

app.py를 수정한 뒤에는 이 스크립트를 다시 실행하세요:  python build_notebook.py
노트북에는 비밀값이 들어가지 않습니다 (Colab Secrets에서 읽음).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(keepends=True)}


with open(os.path.join(HERE, "app.py"), encoding="utf-8") as f:
    app_src = f.read()

cells = [
    md("""
# 🎬 VideoDigest 백엔드 (Colab + ngrok)

3·4단계(캡션·요약)는 **Qwen2.5-VL-3B-Instruct** 를 이 Colab GPU에서 직접 실행합니다. API 키·비용이 필요 없습니다.

**처음 한 번만 준비**
1. 메뉴 **런타임 → 런타임 유형 변경 → T4 GPU** (필수 · CPU로는 너무 느립니다)
2. 왼쪽 🔑 **Secrets** 에 아래 이름으로 값을 추가하고, 각 항목의 *노트북 액세스* 를 켭니다.
   - `NGROK_AUTHTOKEN` (필수) — https://dashboard.ngrok.com/get-started/your-authtoken
   - `NGROK_DOMAIN` (권장) — ngrok 무료 고정 도메인 `xxx.ngrok-free.dev` (https://dashboard.ngrok.com/domains)
   - `ALLOWED_ORIGINS` (선택) — 허용할 프론트 주소, 쉼표 구분
   - `CAPTION_BACKEND` (선택) — `openai`로 두면 gpt-5-mini API 사용 (이때만 `OPENAI_API_KEY` 필요)

**실행**: 메뉴 **런타임 → 모두 실행**. 마지막 셀에 `🌐 공개 API URL` 이 나오면 접속 가능,
`[VLM] 준비 완료` 가 나오면 모델까지 준비 완료입니다 (첫 실행은 모델 약 7GB 다운로드로 몇 분 걸림).
마지막 셀이 실행 중인 동안만 서버가 살아 있습니다 (셀 중지 = 서버 종료).
"""),
    md("## 1. 패키지 설치\nColab에 이미 있는 torch·opencv는 다시 설치하지 않습니다. Qwen2.5-VL은 transformers 4.49 이상이 필요합니다."),
    code("""
!pip -q install flask flask-cors pyngrok openai python-dotenv "transformers>=4.49"
import torch
print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "없음 ✖ — 런타임 → 런타임 유형 변경 → T4 GPU")
"""),
    md("## 2. Secrets → 환경변수\n값은 화면에 출력하지 않습니다."),
    code("""
import os
from google.colab import userdata

def secret(name, required=False):
    try:
        value = userdata.get(name)
    except Exception:  # 없거나 노트북 액세스가 꺼져 있음
        value = None
    if value:
        os.environ[name] = value.strip()
    elif required:
        raise RuntimeError(f"Colab Secrets에 {name}이(가) 없거나 노트북 액세스가 꺼져 있습니다.")
    print(f"{name:16s}: {'설정됨 ✔' if value else ('없음 ✖' if required else '없음 (선택)')}")

secret("NGROK_AUTHTOKEN", required=True)
secret("NGROK_DOMAIN")
secret("ALLOWED_ORIGINS")
secret("CAPTION_BACKEND")       # 선택 · 기본 local(Qwen2.5-VL). openai로 두면 아래 키 필요
secret("OPENAI_API_KEY", required=os.environ.get("CAPTION_BACKEND", "local").lower() == "openai")
secret("OPENAI_MODEL")          # 선택 · openai일 때 모델 (기본 gpt-5-mini)
secret("PRICE_INPUT_PER_1M")    # 선택 · 대시보드 'API 단가 환산' 비용
secret("PRICE_OUTPUT_PER_1M")
os.environ["PYTHONUNBUFFERED"] = "1"   # 로그(유사도 표)를 실시간 출력
"""),
    md("## 3. 백엔드 코드 저장\n`backend/app.py`와 같은 내용입니다. (수정은 app.py에서 하고 `python build_notebook.py`로 노트북을 다시 만드세요.)"),
    code("%%writefile app.py\n" + app_src),
    md("## 4. 서버 실행 + ngrok 공개 URL\n이 셀은 계속 실행 상태로 둡니다. 출력에 모델 로드 상황, DINO 유사도 표, 캡션 등 처리 로그가 나옵니다."),
    code("!python app.py"),
]

nb = {
    "cells": cells,
    "metadata": {
        "colab": {"provenance": []},
        "kernelspec": {"display_name": "Python 3", "name": "python3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 0,
}

out = os.path.join(HERE, "colab_backend.ipynb")
with open(out, "w", encoding="utf-8") as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)
print("생성:", out)
