import 'server-only';
import { createClient } from '@supabase/supabase-js';
import sampleJobs from './sample-jobs.json';
import type { Job, JobResult } from './types';

export async function getJobs(): Promise<JobResult> {
 const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
 const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim();
 if (!url && !key) return { jobs: sampleJobs as Job[], source: 'sample' };
 if (!url || !key) return { jobs: [], source: 'error', message: 'Supabase 연결 설정이 완성되지 않았어요. URL과 Publishable key를 모두 설정하고 서버를 다시 시작해 주세요.' };
 try {
  const client = createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false }, global: { fetch: (input, init) => fetch(input, { ...init, cache: 'no-store', signal: AbortSignal.timeout(10000) }) } });
  const { data, error } = await client.from('hy_company_jobs').select('id,title,department,location,employment,experience,summary,responsibilities,requirements,tags,published,sort_order,application_url').eq('published', true).order('sort_order');
  if (error) throw new Error('query');
  const jobs = data ?? [];
  if (!jobs.every(j => typeof j.id === 'string' && typeof j.title === 'string' && typeof j.department === 'string' && typeof j.summary === 'string' && [j.tags,j.requirements,j.responsibilities].every(a => Array.isArray(a) && a.every(v => typeof v === 'string')))) throw new Error('shape');
  return { jobs: jobs as Job[], source: 'supabase' };
 } catch {
  return { jobs: [], source: 'error', message: '공고를 불러오지 못했어요. Supabase 연결 정보, hy_company_jobs 테이블과 읽기 권한을 확인해 주세요. 연결 오류를 예시 공고로 대신 표시하지 않습니다.' };
 }
}
export function applicationLink(job: Job): string | null {
 const raw = job.application_url || process.env.NEXT_PUBLIC_APPLICATION_FORM_URL;
 if (!raw) return null;
 try { const u = new URL(raw); return u.protocol === 'https:' ? u.href : null; } catch { return null; }
}
