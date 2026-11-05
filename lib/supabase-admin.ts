import 'server-only';
import { createClient, type SupabaseClient } from '@supabase/supabase-js';

/** Secret key 를 쓰는 서버 전용 클라이언트. 키가 없으면 null. */
export function getSupabaseAdmin(): SupabaseClient | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SECRET_KEY;
  if (!url || !key) return null;
  return createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
}

export const AUDIT_BUCKET = process.env.AUDIT_BUCKET ?? 'pii-audit';

export type AuditLog = {
  id: string;
  detected_at: string;
  session_id: string;
  pii_types: string[];
  box_count: number;
  image_path: string;
  frame_width: number | null;
  frame_height: number | null;
};
