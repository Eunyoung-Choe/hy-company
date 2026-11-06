-- VideoDigest 보관함: 요약이 끝날 때마다 날짜·요약·주요 장면(시각·캡션·이미지 경로)을 저장한다.
-- 공유 보관함: 사이트 방문자(anon)가 누구나 읽기·저장·삭제할 수 있다. (팀 결정, 2026-11-06)
-- 장면 이미지는 공개 Storage 버킷 'video-digests'에 JPEG로 저장한다.
-- 다른 테이블은 건드리지 않는다.

create table if not exists public.video_digests (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  title text not null check (char_length(title) between 1 and 200),          -- 업로드한 영상 파일 이름
  summary text not null check (char_length(summary) <= 8000),
  model text check (char_length(model) <= 100),
  duration_sec real check (duration_sec >= 0),
  saved_percent real,
  actual_tokens integer check (actual_tokens >= 0),
  baseline_tokens integer check (baseline_tokens >= 0),
  -- [{ "time": 12.0, "time_label": "00:12", "caption": "...", "failed": false, "image_path": "<id>/0.jpg" }, ...]
  keyframes jsonb not null default '[]'::jsonb
    check (jsonb_typeof(keyframes) = 'array' and jsonb_array_length(keyframes) <= 40)
);

create index if not exists video_digests_created_at_idx on public.video_digests (created_at desc);

alter table public.video_digests enable row level security;
revoke all on table public.video_digests from anon, authenticated;
grant select, insert, delete on table public.video_digests to anon, authenticated;   -- 수정(update)은 허용하지 않음

drop policy if exists "video_digests_read" on public.video_digests;
create policy "video_digests_read" on public.video_digests
  for select to anon, authenticated using (true);

drop policy if exists "video_digests_insert" on public.video_digests;
create policy "video_digests_insert" on public.video_digests
  for insert to anon, authenticated with check (true);

drop policy if exists "video_digests_delete" on public.video_digests;
create policy "video_digests_delete" on public.video_digests
  for delete to anon, authenticated using (true);

-- 장면 이미지 버킷: 공개 읽기(URL), JPEG만, 장당 최대 500KB
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('video-digests', 'video-digests', true, 512000, array['image/jpeg'])
on conflict (id) do nothing;

drop policy if exists "video_digests_images_read" on storage.objects;
create policy "video_digests_images_read" on storage.objects
  for select to anon, authenticated using (bucket_id = 'video-digests');

drop policy if exists "video_digests_images_upload" on storage.objects;
create policy "video_digests_images_upload" on storage.objects
  for insert to anon, authenticated with check (bucket_id = 'video-digests');

drop policy if exists "video_digests_images_delete" on storage.objects;
create policy "video_digests_images_delete" on storage.objects
  for delete to anon, authenticated using (bucket_id = 'video-digests');
