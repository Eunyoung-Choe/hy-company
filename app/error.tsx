'use client';
export default function ErrorPage({reset}:{reset:()=>void}){return <main id="main" className="detail"><h1>화면을 불러오지 못했어요.</h1><p>잠시 후 다시 시도해 주세요.</p><button className="primary-link" onClick={reset}>다시 시도하기</button></main>;}
