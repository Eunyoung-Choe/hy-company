-- PII 마스킹 감사 로그: 마스킹이 끝난 결과물 이미지 경로와 감지 유형만 저장한다.
-- 인식된 개인정보 텍스트는 저장하지 않는다.
-- 읽기/쓰기는 Secret key(에이전트, Next.js 서버)만 가능. anon/authenticated 에는 권한 없음.

create table if not exists public.pii_audit_logs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  detected_at timestamptz not null default now(),
  session_id text not null,
  pii_types text[] not null check (cardinality(pii_types) > 0),
  box_count integer not null check (box_count >= 0),
  image_path text not null,
  frame_width integer,
  frame_height integer
);

create index if not exists pii_audit_logs_detected_at_idx on public.pii_audit_logs (detected_at desc);

alter table public.pii_audit_logs enable row level security;
revoke all on table public.pii_audit_logs from anon, authenticated;
-- 정책 없음: RLS가 켜진 상태에서 anon/authenticated 는 아무 행도 접근할 수 없다.

-- 비공개 Storage 버킷 (공개 URL 없음, 서버가 만든 서명 URL로만 열람)
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('pii-audit', 'pii-audit', false, 5242880, array['image/jpeg'])
on conflict (id) do nothing;
