'use client';

import { useRouter } from 'next/navigation';

/** 이전 페이지로. 새 탭에서 바로 열어 돌아갈 곳이 없으면 첫 화면으로 간다. */
export default function BackButton({ fallback = '/' }: { fallback?: string }) {
  const router = useRouter();
  return (
    <button
      type="button"
      className="btn small"
      onClick={() => (window.history.length > 1 ? router.back() : router.push(fallback))}
    >
      ← 이전
    </button>
  );
}
