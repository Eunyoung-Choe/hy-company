import Link from 'next/link';
export default function NotFound(){return <main id="main" className="detail"><p className="eyebrow">404</p><h1>찾으시는 페이지가 없어요.</h1><p>주소가 바뀌었거나 공개되지 않은 공고일 수 있어요.</p><Link className="primary-link" href="/#positions">공고 목록으로 돌아가기 ↗</Link></main>;}
