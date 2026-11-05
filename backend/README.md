# VideoDigest 백엔드 (Google Colab + ngrok)

OpenCV → DINOv2 → gpt-5.4-mini(캡션) → gpt-5.4-mini(텍스트 요약) 4단계 파이프라인 Flask API.
1·2단계로 영상 대부분을 걸러 내고, 남은 키프레임만 저해상도로 GPT에 보내 토큰을 아낍니다.

## Colab에서 실행

1. `colab_backend.ipynb`를 Colab에서 엽니다 (파일 → 노트북 업로드).
2. 왼쪽 🔑 Secrets에 `OPENAI_API_KEY`, `NGROK_AUTHTOKEN`, (권장) `NGROK_DOMAIN`을 추가하고 노트북 액세스를 켭니다. 모델 단가는 `PRICE_INPUT_PER_1M`, `PRICE_OUTPUT_PER_1M`으로 맞춥니다. (T4 GPU는 선택 — DINOv2가 빨라짐)
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
