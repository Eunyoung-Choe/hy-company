import Link from 'next/link';
import { notFound } from 'next/navigation';
import { getJobs, applicationLink } from '@/lib/jobs';
export const dynamic = 'force-dynamic';
export default async function JobDetail({ params }: { params: Promise<{ id: string }> }) {
 const { id } = await params;
 const result = await getJobs();
 if (result.source === 'error') return <main id="main" className="detail"><Link className="back-link" href="/#positions">← 모든 공고</Link><div className="error-box" role="alert"><h1>공고를 불러오지 못했어요.</h1><p>{result.message}</p><a href={'/jobs/'+encodeURIComponent(id)}>다시 시도하기 ↗</a></div></main>;
 const job = result.jobs.find(j => j.id === id); if (!job) notFound();
 const apply = applicationLink(job);
 return <main id="main" className="detail"><Link className="back-link" href="/#positions">← 모든 공고</Link><div className="detail-heading"><p className="eyebrow">{job.department} · HY COMPANY</p><h1>{job.title}</h1><p>{job.summary}</p><div className="tags">{job.tags.map(t=><span key={t}>{t}</span>)}</div></div><div className="detail-grid"><div className="detail-body"><section><h2>함께할 일</h2><ul>{job.responsibilities.map(t=><li key={t}>{t}</li>)}</ul></section><section><h2>이런 동료를 기다려요</h2><ul>{job.requirements.map(t=><li key={t}>{t}</li>)}</ul></section><section><h2>서로 알아가는 과정</h2><p>지원서 확인 → 경험 나누기 → 함께할 준비</p><p className="muted">실습용 가상 공고입니다. 실제 채용 절차는 진행되지 않습니다.</p></section></div><aside className="apply-card"><p className="eyebrow">YOUR NEXT STEP</p><h2>새로운 시작을 함께해요.</h2><dl><div><dt>직무</dt><dd>{job.department}</dd></div><div><dt>경력</dt><dd>{job.experience}</dd></div><div><dt>고용 형태</dt><dd>{job.employment}</dd></div><div><dt>근무 지역</dt><dd>{job.location}</dd></div></dl>{apply?<a className="primary-link" href={apply} target="_blank" rel="noopener noreferrer">지원 폼 열기 ↗</a>:<><button className="primary-link" disabled>지원 폼 준비 중</button><p className="muted">실습용 지원 폼을 연결하면<br/>이곳에서 열 수 있어요.</p></>}<p className="sample-note">실습에는 개인정보 없는 테스트 내용만 사용해 주세요.</p></aside></div></main>;
}
