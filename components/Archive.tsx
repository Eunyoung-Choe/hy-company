'use client';

import { useCallback, useEffect, useState } from 'react';
import { deleteDigest, imageUrl, listDigests, PAGE_SIZE, type Digest } from '@/lib/digests';

const when = new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' });
const nf = new Intl.NumberFormat('ko-KR');

function fmtDuration(sec: number | null): string {
  if (sec == null) return '';
  const m = Math.floor(sec / 60), s = Math.round(sec % 60);
  return m ? `${m}분 ${s}초` : `${s}초`;
}

/** 보관함: 요약 기록을 날짜순으로 보여주고, 펼치면 요약과 주요 장면을 열람한다. refreshKey가 바뀌면 다시 불러온다. */
export default function Archive({ refreshKey }: { refreshKey: number }) {
  const [items, setItems] = useState<Digest[]>([]);
  const [loading, setLoading] = useState(true);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState('');
  const [openId, setOpenId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = useCallback(async (before?: string) => {
    setLoading(true);
    setError('');
    try {
      const page = await listDigests(before);
      setItems((prev) => (before ? [...prev, ...page] : page));
      setHasMore(page.length === PAGE_SIZE);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load, refreshKey]);

  async function remove(d: Digest) {
    if (!window.confirm(`"${d.title}" 기록을 삭제할까요?\n공유 보관함이라 다른 사람에게서도 사라져요.`)) return;
    setDeleting(d.id);
    setError('');
    try {
      await deleteDigest(d);
      setItems((prev) => prev.filter((x) => x.id !== d.id));
      if (openId === d.id) setOpenId(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setDeleting(null);
    }
  }

  return (
    <div className="win-body archive">
      <div className="archive-head">
        <p className="hint">요약이 끝나면 자동으로 저장돼요.</p>
        <button type="button" className="btn small" onClick={() => load()} disabled={loading}>새로고침 ↻</button>
      </div>
      {error && <p className="alert" role="alert">⚠ {error}</p>}
      {!loading && !error && items.length === 0 && <p className="empty">아직 저장된 요약이 없어요. 영상을 요약하면 여기에 쌓여요.</p>}

      <ul className="digests">
        {items.map((d) => {
          const open = openId === d.id;
          return (
            <li key={d.id} className={'digest' + (open ? ' open' : '')}>
              <button type="button" className="digest-row" aria-expanded={open} onClick={() => setOpenId(open ? null : d.id)}>
                <span className="digest-date">{when.format(new Date(d.created_at))}</span>
                <span className="digest-title">{d.title}</span>
                <span className="digest-meta">
                  장면 {d.keyframes.length}장
                  {d.saved_percent != null && <> · 토큰 <b>{d.saved_percent}%</b> 절약</>}
                  {d.duration_sec != null && <> · {fmtDuration(d.duration_sec)}</>}
                </span>
                <span className="digest-caret" aria-hidden>{open ? '▲' : '▼'}</span>
              </button>
              {open && (
                <div className="digest-body">
                  <p className="summary">{d.summary}</p>
                  {d.actual_tokens != null && d.baseline_tokens != null && (
                    <p className="note">실제 {nf.format(d.actual_tokens)} 토큰 / 통째로 넣었다면 {nf.format(d.baseline_tokens)} 토큰{d.model ? ` · ${d.model}` : ''}</p>
                  )}
                  <div className="gallery">
                    {d.keyframes.map((k) => (
                      <figure key={k.image_path} className="shot">
                        <div className="shot-img">
                          <img src={imageUrl(k.image_path)} alt={`${k.time_label} 장면`} loading="lazy" />
                          <span className="stamp">{k.time_label}</span>
                        </div>
                        <figcaption className={k.failed ? 'failed' : undefined}>{k.caption}</figcaption>
                      </figure>
                    ))}
                  </div>
                  <div className="actions">
                    <button type="button" className="btn danger" onClick={() => remove(d)} disabled={deleting === d.id}>
                      {deleting === d.id ? '삭제 중…' : '🗑 이 기록 삭제'}
                    </button>
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>

      {loading && <p className="hint">불러오는 중…</p>}
      {hasMore && !loading && (
        <div className="actions">
          <button type="button" className="btn" onClick={() => load(items[items.length - 1]?.created_at)}>이전 기록 더 보기</button>
        </div>
      )}
    </div>
  );
}
