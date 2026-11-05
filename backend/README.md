# VideoDigest 백엔드 (Google Colab + ngrok)

OpenCV → DINOv2 → Qwen2.5-VL-3B(캡션) → Qwen2.5-VL-3B(텍스트 요약) 4단계 파이프라인 Flask API.
3·4단계는 Colab GPU에서 로컬 실행합니다 (API 키·비용 없음). `CAPTION_BACKEND=openai`로 gpt-5-mini API를 쓸 수도 있습니다.

## Colab에서 실행

1. `colab_backend.ipynb`를 Colab에서 엽니다 (파일 → 노트북 업로드).
2. 런타임 → 런타임 유형 변경 → **T4 GPU**. 왼쪽 🔑 Secrets에 `NGROK_AUTHTOKEN`, (권장) `NGROK_DOMAIN`을 추가하고 노트북 액세스를 켭니다.
3. 런타임 → 모두 실행 → 마지막 셀의 `🌐 공개 API URL` 확인.
4. 그 주소를 프론트엔드 `NEXT_PUBLIC_API_URL`에 넣습니다 (로컬은 `.env.local`, 배포는 Vercel 환경변수 + 재배포).

마지막 셀이 실행 중인 동안만 서버가 살아 있습니다. Colab 무료 런타임은 장시간 미사용·최대 사용 시간이 지나면 끊깁니다.

## app.py를 수정했다면

```sh
python build_notebook.py   # colab_backend.ipynb 다시 생성
```

## 로컬 실행

```sh
pip install -r requirements.txt
cp .env.example .env       # 값 입력 (NGROK_AUTHTOKEN 없으면 localhost:5000에서만 실행)
python app.py
```

## API

- `GET /api/health` 상태 확인
- `POST /api/upload` (form-data `video`, MP4) → `{ "job_id" }`
- `GET /api/jobs/<job_id>` 진행 상황·결과
