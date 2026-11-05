# 새 프로젝트

Next.js + Supabase + Vercel 배포 환경만 남긴 시작 상태입니다.

- 개발 서버: `npm ci` → `npm run dev`
- 확인: `npm run build`, `npm run typecheck`
- 코드 배포: `main` 브랜치에 push하면 Vercel이 자동 배포
- DB 변경: `supabase/migrations`에 SQL 추가 → `npx supabase db push --remote` (GitHub push로는 DB가 바뀌지 않음)
- 연결값: `.env.example`을 `.env.local`로 복사해 Supabase URL과 Publishable key 입력 (Git에 올리지 않음)
