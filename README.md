# PII Guard — 실시간 화면 개인정보 마스킹

화면을 캡처해 주민등록번호·카드번호·계좌번호·CVC/OTP·주소·휴대폰 번호를 찾아 가린 뒤,
**마스킹된 결과물만** 원격 화면으로 송출하고 Supabase에 감사 로그를 남깁니다.

```
agent/   Python 마스킹 에이전트 (캡처 → OCR/Regex → 마스킹 → 송출·감사 로그)
app/     Next.js 화면  /pii (PII Guard 홈) · /pii/demo 데모 자료 · /pii/viewer 원격 화면 · /pii/audit 감사 로그
supabase/migrations/  감사 로그 테이블 + 비공개 Storage 버킷
```

## 처리 흐름

| 단계 | 담당 | 내용 |
| --- | --- | --- |
| 1 | CPU · mss | 60FPS 캡처 → 미리 할당한 Ring Buffer A 슬롯에 덮어쓰기 (파일 저장 없음) |
| 2 | Windows 내장 OCR(없으면 EasyOCR) + Regex | PII 좌표(BBOX)만 추출, 인식 텍스트는 즉시 폐기 |
| 3 | CPU · OpenCV | PII 좌표에 검은 박스. **OCR 검증 전 변경 영역은 직전 검증본으로 보류, 새로 드러난 영역은 모자이크 (Fail-closed)** |
| 4 | 비동기 스레드 | 마스킹 완성본만 MJPEG 송출, PII 감지 시 마스킹본만 Supabase 업로드 |

OCR은 송출(60FPS)보다 느립니다(Windows OCR: 바뀐 띠 약 0.1초, 화면 전체 약 0.8초 / EasyOCR CPU: 수 초).
그래서 마지막 검증 프레임과 달라진 영역은 OCR이 다시 확인할 때까지 직전 검증본(이미 마스킹됨)으로 보여줍니다.
새로 뜬 개인정보가 검증 전에 송출되지 않게 하기 위해서입니다.

**스크롤 보정:** 화면이 세로로 밀린 것을 찾으면 검증된 화면·PII 박스를 같이 옮기고, 새로 드러난 띠만 모자이크한 뒤
그 띠만 OCR합니다. 그래서 스크롤해도 화면이 멈추지 않습니다. 옮겨도 맞지 않는 곳(고정 헤더 등)은 그대로 검증 대기입니다.

**녹화:** 뷰어의 녹화 버튼은 송출과 같은 마스킹 완성본만 MP4(H.264)로 저장합니다. 종료하면 다른 이름으로 저장 창이 열립니다.

## 실행

### 1) 웹
```bash
npm ci
cp .env.example .env.local   # 값 입력
npm run dev                  # http://localhost:3000
```

### 2) 에이전트 (Python 3.13 권장)
```bash
cd agent
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
cp .env.example .env         # 캡처 영역, Supabase 값 입력
.venv/Scripts/python -m pii_guard
```
Windows에서는 내장 OCR을 씁니다(설정 → 시간 및 언어 → 언어에 **한국어**가 있어야 함).
쓸 수 없으면 EasyOCR로 바뀌며, 이때는 첫 실행 때 모델(약 100MB)을 내려받습니다.
EasyOCR은 NVIDIA GPU가 있으면 CUDA용 torch를 따로 설치해야 GPU로 동작합니다.

### 3) 시연
모니터가 하나라면 `/pii/demo` 창은 왼쪽 절반에, `/pii/viewer` 창은 오른쪽 절반에 두세요.
그리고 `agent/.env`에서 `CAPTURE_REGION`을 왼쪽 절반으로 지정합니다(예: `0,0,960,1040`).
뷰어 창까지 캡처하면 화면 속 화면이 무한히 반복됩니다.
`/pii/demo`에서 **새 고객 불러오기**를 누르면 바뀐 영역이 모자이크 → 검은 박스로 바뀌는 과정을 볼 수 있습니다.

### 4) 감사 로그 DB
```bash
npx supabase db push --remote
```
`/pii/audit`와 에이전트는 **Secret key**를 씁니다. 이 키는 서버와 에이전트 전용입니다.
테이블과 버킷은 anon/authenticated 권한이 없고, 이미지는 10분짜리 서명 URL로만 열립니다.
> `/pii/audit`에는 로그인이 없습니다. Vercel에 배포하는 환경에는 `SUPABASE_SECRET_KEY`를 넣지 말거나, 먼저 인증을 추가하세요.

## 확인
- 웹: `npm run typecheck`, `npm run build`
- 에이전트: `cd agent && .venv/Scripts/python -m unittest discover -s tests -t .`

## 보안상 한계 (과장 금지)
- 원본 픽셀은 디스크에 저장하지 않고 RAM에만 잠깐 존재합니다.
  다만 캡처 라이브러리와 numpy·OpenCV 내부 복사본, 해제 후 0으로 지워지지 않는 VRAM, OS 페이지 파일까지 완전히 지운다고 보장하지는 않습니다.
- OCR이 놓친 개인정보(작은 글씨, 이미지 속 글자, 손글씨 등)는 가려지지 않습니다.
  주소처럼 정형화되지 않은 정보는 휴리스틱으로 찾습니다.
- 개발 시연용 송출(MJPEG)은 `127.0.0.1` 전용입니다. 실제 원격 송출에는 WebRTC 등 암호화된 전송이 필요합니다.

## 배포 메모
- 코드 배포: `main` 브랜치에 push하면 Vercel이 자동 배포합니다.
- DB 변경: GitHub push로는 반영되지 않습니다. `npx supabase db push --remote`를 실행해야 합니다.
