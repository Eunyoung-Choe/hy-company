import { connection } from 'next/server';
import { AUDIT_BUCKET, getSupabaseAdmin, type AuditLog } from '@/lib/supabase-admin';
import { piiLabel } from '@/lib/pii';
import PiiHeader from '../PiiHeader';

export const metadata = { title: '감사 로그' };

async function loadLogs() {
  await connection(); // 요청마다 최신 로그 조회 (빌드 시 미리 렌더링하지 않음)
  const sb = getSupabaseAdmin();
  if (!sb) return { configured: false as const };

  const { data, error } = await sb
    .from('pii_audit_logs')
    .select('id, detected_at, session_id, pii_types, box_count, image_path, frame_width, frame_height')
    .order('detected_at', { ascending: false })
    .limit(60);
  if (error) return { configured: true as const, error: error.message, logs: [] };

  const logs = (data ?? []) as AuditLog[];
  const urls = new Map<string, string>();
  if (logs.length) {
    const { data: signed } = await sb.storage
      .from(AUDIT_BUCKET)
      .createSignedUrls(logs.map((l) => l.image_path), 600); // 10분짜리 서명 URL
    signed?.forEach((s) => s.path && s.signedUrl && urls.set(s.path, s.signedUrl));
  }
  return { configured: true as const, logs: logs.map((l) => ({ ...l, url: urls.get(l.image_path) })) };
}

export default async function AuditPage() {
  const result = await loadLogs();

  return (
    <main className="desk wide">
      <PiiHeader lead="감사 로그">
        개인정보가 감지된 시점의 <strong>마스킹 완성본</strong>만 저장됩니다. 인식된 텍스트는 저장하지 않습니다.
      </PiiHeader>
      <section className="win">
        <div className="win-title">🗂 감지 기록</div>
        <div className="win-body">

      {!result.configured ? (
        <div className="notice">
          <strong>Supabase 서버 키가 설정되지 않았습니다.</strong>
          <p>
            <code>.env.local</code>에 <code>NEXT_PUBLIC_SUPABASE_URL</code>과 <code>SUPABASE_SECRET_KEY</code>를 넣고
            개발 서버를 다시 시작하세요. Secret key는 서버에서만 사용되며 브라우저로 전달되지 않습니다.
          </p>
        </div>
      ) : 'error' in result && result.error ? (
        <p className="alert" role="alert">조회 실패: {result.error}</p>
      ) : result.logs.length === 0 ? (
        <p className="empty">아직 기록이 없습니다. 에이전트를 실행하고 데모 자료를 띄워 보세요.</p>
      ) : (
        <ul className="audit-grid">
          {result.logs.map((l) => (
            <li key={l.id} className="audit-item">
              {l.url ? (
                <a href={l.url} target="_blank" rel="noreferrer">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={l.url} alt="마스킹된 감사 로그 이미지" loading="lazy" />
                </a>
              ) : (
                <div className="img-missing">이미지 없음</div>
              )}
              <div className="audit-meta">
                <div className="chips">
                  {l.pii_types.map((k) => <span key={k} className="chip">{piiLabel(k)}</span>)}
                </div>
                <small className="muted">
                  {new Date(l.detected_at).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} · {l.session_id} · 박스 {l.box_count}개
                </small>
              </div>
            </li>
          ))}
        </ul>
      )}
        </div>
      </section>
    </main>
  );
}
