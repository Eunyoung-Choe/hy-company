'use client';
import { useState } from 'react';
import Link from 'next/link';
import type { Job } from '@/lib/types';
export default function JobBoard({ jobs }: { jobs: Job[] }) {
 const [department,setDepartment] = useState('전체');
 const categories = ['전체',...new Set(jobs.map(j => j.department))];
 const visible = jobs.filter(j => department === '전체' || j.department === department);
 return <><div className="filters" role="group" aria-label="직무 선택">{categories.map(c => <button key={c} aria-pressed={department === c} onClick={() => setDepartment(c)}>{c}</button>)}</div><p className="result-count" aria-live="polite">열려 있는 기회 <strong>{visible.length}</strong></p><div className="job-grid">{visible.map(j => <Link className="job-card" key={j.id} href={'/jobs/'+encodeURIComponent(j.id)}><div className="card-top"><span className="department">{j.department}</span><span aria-hidden="true">↗</span></div><h3>{j.title}</h3><p>{j.summary}</p><div className="tags">{j.tags.map(t => <span key={t}>{t}</span>)}</div><div className="card-meta">{j.experience}<span>·</span>{j.employment}<span>·</span>{j.location}</div></Link>)}</div>{!visible.length && <div className="empty">아직 등록된 공고가 없어요. 새로운 기회를 준비하고 있습니다.</div>}</>;
}
