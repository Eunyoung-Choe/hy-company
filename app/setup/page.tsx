import Link from 'next/link';
import CopyBox from '@/components/CopyBox';
import { getJobs } from '@/lib/jobs';
import guide from '@/lib/setup-guide.json';
export const dynamic = 'force-dynamic';
export const metadata = { title: 'CLI 연결 실습 안내' };
export default async function Setup() {
 const result = await getJobs();
 return <main id="main" className="setup-page"><p className="eyebrow">HY COMPANY · CLI SETUP</p><h1>이 문장을 AI에게 보내세요.</h1><p className="setup-intro">Supabase CLI와 Vercel CLI로 연결하고 배포해요.<br/>아래 요청을 복사해 <strong>hy-company 폴더의 Claude Code</strong>에 붙여넣으세요.</p><div className="setup-flow"><b>프롬프트 복사</b><span>→</span><b>AI 안내 따라 로그인</b><span>→</span><b>연결 · 배포 확인</b></div><CopyBox text={guide.prompt} label="CLI 연결 프롬프트 복사" expanded/><ol className="setup-steps"><li><span className="setup-number">01</span><div><h2>복사한 요청을 Claude Code에 보내요.</h2><p>지금 프로젝트 폴더에서 실행 중인 Claude Code에 붙여넣고 Enter를 눌러요.<br/>AI가 설치된 CLI를 확인하고 연결 작업을 순서대로 진행합니다.</p></div></li><li><span className="setup-number">02</span><div><h2>로그인과 프로젝트 선택은 직접 해요.</h2><p>AI가 알려주는 인증 주소를 열고 내 계정으로 로그인해요.<br/>내 조직·프로젝트를 선택하고 필요한 비밀번호는 직접 입력해요.</p><p className="muted">명령 실행 승인을 요청하면 내용을 확인하고 진행해요. 키나 비밀번호를 단톡방에 올리지 않아요.</p></div></li><li><span className="setup-number">03</span><div><h2>이 화면과 공개 주소에서 확인해요.</h2><p>Supabase 연결 후 서버를 다시 실행하고 아래 상태를 새로고침해요.<br/>Vercel 배포가 끝나면 AI가 알려준 공개 주소에서도 공고를 확인해요.</p></div></li></ol><div className={'setup-status '+(result.source==='error'?'bad':'')}><strong>{result.source==='supabase'?`Supabase 연결됨 · 공개 공고 ${result.jobs.length}건`:result.source==='sample'?'서버 실행됨 · Supabase는 아직 미연결':'서버 실행됨 · Supabase 연결 확인 필요'}</strong><p>{result.source==='supabase'?'실제 DB에서 공고를 읽었습니다.':result.source==='sample'?'홈 화면은 로컬 예시 공고로 열립니다. 위 요청으로 실제 DB를 연결해 주세요.':result.message}</p><a href="/setup">연결 상태 새로고침 ↻</a><Link href="/">채용 사이트 열기 ↗</Link></div><p className="muted">이 상태는 DB 조회 결과입니다. Vercel·GitHub 인증이나 배포 성공은 CLI 결과와 공개 주소에서 별도로 확인해요.<br/>“나의 채용 분석” 탭은 강의 34번에서 함께 추가합니다.</p></main>;
}
