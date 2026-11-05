'use client';
import { useState } from 'react';
export default function CopyBox({ text, label = '복사', expanded = false }: { text: string; label?: string; expanded?: boolean }) {
 const [status, setStatus] = useState('');
 async function copy() {
  try {
   try { await navigator.clipboard.writeText(text); }
   catch { const el = document.createElement('textarea'); el.value = text; document.body.append(el); el.select(); const ok = document.execCommand('copy'); el.remove(); if (!ok) throw new Error('copy'); }
   setStatus('복사했어요.');
  } catch { setStatus('아래 내용을 직접 선택해 복사해 주세요.'); }
 }
 return <div className="setup-copy"><div><button onClick={copy}>{label}</button><span role="status">{status}</span></div><details open={expanded}><summary>복사할 내용 보기</summary><pre>{text}</pre></details></div>;
}
