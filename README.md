# HY컴퍼니 · 공통 실습 시작 프로젝트

한양여자대학교 AI 해커톤에서 모두 같은 상태로 시작하기 위한 Next.js 프로젝트입니다.
## 서버 실행 → 브라우저에서 연결

Node.js 24 LTS 권장(최소 22). `hy-company` 폴더에서 아래 두 줄만 실행합니다.

```sh
npm ci
npm run dev
```

터미널에 표시된 주소 뒤에 `/setup`을 붙여 엽니다. 보통 **http://localhost:3000/setup** 입니다.

이 서버 페이지의 **CLI 연결 프롬프트를 Claude Code에 보내고**, AI 안내에 따라 Supabase CLI와 Vercel CLI로 연결·배포합니다. Next.js 서버가 Supabase에서 공고를 읽어 화면을 제공합니다. 서버를 별도로 하나 더 만들 필요가 없습니다.

- `/`: 채용 사이트
- `/setup`: 연결 가이드와 실제 DB 연결 상태
- `/jobs/[id]`: 공고 상세

설치 전 도움이 필요하면 `시작하기.html`, 자세한 절차는 `docs/학생시작가이드.md`를 참고하세요.

## 포함한 것

- 가상 기업 HY컴퍼니 소개, 예시 채용공고 6개, 직무 필터, 공고 상세.
- Supabase 연결 전 로컬 예시 모드 / 연결 후 실제 DB 조회 / 연결 실패·빈 결과 구분.
- 공개 실습 공고만 읽을 수 있는 Supabase 테이블·RLS·예시 SQL.
- GitHub 첫 저장소 생성과 Vercel 자동 배포 안내.
- 선택적으로 Google Form 응답 링크 연결. 기본 지원 버튼은 비활성화.
- 로컬 글꼴을 포함하므로 화면을 위해 별도 글꼴 서버에 접속하지 않습니다.

## 수업에서 추가할 것

34번 슬라이드에서 헤더에 기존 `/` 페이지 탭과 `/career` 분석 탭을 추가합니다. 이후 커리어리 MCP 데이터 적재, 차트, 이력서 추천을 구현합니다. 시작 프로젝트에는 해당 기능이나 MCP 팀 토큰을 미리 넣지 않았습니다.

## 연결 정보

`.env.example`을 `.env.local`로 복사해 내 Supabase URL과 Publishable key를 입력합니다. 실제 값은 GitHub·단톡방에 올리지 않습니다. AI가 `supabase/01_hy_company.sql`을 마이그레이션으로 준비하고 Supabase CLI로 반영합니다. Vercel 환경변수도 CLI로 별도 설정합니다.

이 ZIP은 프로젝트·계정·배포를 자동 생성하지 않습니다. 본인 계정으로 안내 절차를 완료해야 연결됩니다.

## 파일 구조

- `app/page.tsx`: 채용 홈 화면
- `app/jobs/[id]/page.tsx`: 상세 화면과 지원 링크
- `components/Header.tsx`: 34번에서 수정할 헤더
- `components/JobBoard.tsx`: 직무 필터와 공고 카드
- `lib/jobs.ts`: Supabase 조회와 오류 처리
- `lib/sample-jobs.json`: 연결 전 사용할 가상 공고
- `supabase/01_hy_company.sql`: 학생 DB 초기 설정
- `docs/학생시작가이드.md`: 계정 생성부터 공개 주소까지

## 검증

```sh
npm run build
npm run typecheck
npm start
```

개발 중에는 `npm run dev`를 사용합니다. `npm start`는 먼저 빌드해야 합니다. 설치 버전은 `package-lock.json`에 고정되어 있으므로 `npm ci`를 사용합니다.

## 배포 흐름

코드 수정 → 필요한 DB 변경 별도 적용 → commit → GitHub 배포 브랜치에 push → Vercel 빌드·배포 → 공개 주소 확인.

Supabase 테이블을 GitHub push만으로 바꿀 수는 없습니다. 현재 프로젝트에는 자동 DB 마이그레이션 설정이 없습니다.

글꼴: Pretendard, SIL Open Font License. `public/fonts/LICENSE.txt`를 참고하세요.
