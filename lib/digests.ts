// VideoDigest 보관함 (Supabase): 요약 결과를 날짜와 함께 저장·열람·삭제.
// 공유 보관함이라 브라우저에서 공개용 Publishable key로 직접 접근합니다. (secret 키 사용 안 함)
// 허용 범위는 DB의 RLS 정책·제약 조건이 정합니다: supabase/migrations/*_video_digests.sql
import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import type { JobResult } from './api';

const URL = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
const KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim();
const BUCKET = 'video-digests';
const TABLE = 'video_digests';

export type StoredKeyframe = { time: number; time_label: string; caption: string; failed: boolean; image_path: string };

export type Digest = {
  id: string;
  created_at: string;
  title: string;
  summary: string;
  model: string | null;
  duration_sec: number | null;
  saved_percent: number | null;
  actual_tokens: number | null;
  baseline_tokens: number | null;
  keyframes: StoredKeyframe[];
};

let client: SupabaseClient | null = null;

function db(): SupabaseClient {
  if (!URL || !KEY) {
    throw new Error('보관함을 쓰려면 NEXT_PUBLIC_SUPABASE_URL과 NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY가 필요해요 (.env.local / Vercel 환경변수).');
  }
  client ??= createClient(URL, KEY, { auth: { persistSession: false, autoRefreshToken: false } });
  return client;
}

export function imageUrl(path: string): string {
  return db().storage.from(BUCKET).getPublicUrl(path).data.publicUrl;
}

function base64ToBlob(b64: string): Blob {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: 'image/jpeg' });
}

/** 요약 결과 저장: 장면 이미지를 Storage에 올린 뒤 보관함 행을 만든다. 실패하면 올린 이미지를 지우고 오류를 그대로 던진다. */
export async function saveDigest(title: string, r: JobResult): Promise<string> {
  const sb = db();
  const id = crypto.randomUUID();
  const paths = r.keyframes.map((_, i) => `${id}/${String(i).padStart(2, '0')}.jpg`);
  try {
    await Promise.all(r.keyframes.map(async (k, i) => {
      // cacheControl 60초: 공개 URL은 CDN에 캐시되므로, 삭제 후에도 이전 주소로 보이는 시간을 짧게(기본 1시간 → 1분)
      const { error } = await sb.storage.from(BUCKET).upload(paths[i], base64ToBlob(k.image),
        { contentType: 'image/jpeg', cacheControl: '60' });
      if (error) throw new Error(`장면 이미지 저장 실패: ${error.message}`);
    }));
    const { error } = await sb.from(TABLE).insert({
      id,
      title: title.slice(0, 200) || '이름 없는 영상',
      summary: r.summary.slice(0, 8000),
      model: r.metrics.engine,
      duration_sec: r.funnel.duration,
      saved_percent: r.metrics.saved_percent,
      actual_tokens: r.metrics.actual_tokens,
      baseline_tokens: r.metrics.baseline_tokens,
      keyframes: r.keyframes.map((k, i) => ({
        time: k.time, time_label: k.time_label, caption: k.caption, failed: !!k.failed, image_path: paths[i],
      })),
    });
    if (error) throw new Error(`보관함 저장 실패: ${error.message}`);
    return id;
  } catch (err) {
    await sb.storage.from(BUCKET).remove(paths).catch(() => undefined);   // 반쯤 올라간 이미지 정리
    throw err;
  }
}

export const PAGE_SIZE = 12;

/** 최신순 목록. before(created_at)를 주면 그 이전 기록을 이어서 가져온다. */
export async function listDigests(before?: string): Promise<Digest[]> {
  let q = db().from(TABLE).select('*').order('created_at', { ascending: false }).limit(PAGE_SIZE);
  if (before) q = q.lt('created_at', before);
  const { data, error } = await q;
  if (error) throw new Error(`보관함을 불러오지 못했어요: ${error.message}`);
  return (data ?? []) as Digest[];
}

/** 기록 삭제: 행을 지운 뒤 장면 이미지도 지운다. */
export async function deleteDigest(d: Digest): Promise<void> {
  const sb = db();
  const { error } = await sb.from(TABLE).delete().eq('id', d.id);
  if (error) throw new Error(`삭제 실패: ${error.message}`);
  const paths = d.keyframes.map((k) => k.image_path).filter(Boolean);
  if (paths.length) {
    const { error: e2 } = await sb.storage.from(BUCKET).remove(paths);
    if (e2) throw new Error(`기록은 지웠지만 이미지 정리에 실패했어요: ${e2.message}`);
  }
}
