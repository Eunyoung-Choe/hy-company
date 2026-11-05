// 백엔드(Colab + ngrok) API 통신.
// 로컬은 .env.local, Vercel은 프로젝트 환경변수의 NEXT_PUBLIC_API_URL을 사용합니다.
// NEXT_PUBLIC_ 변수는 빌드 시점에 코드에 박히므로, 값을 바꾸면 다시 빌드·배포해야 합니다.
const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/+$/, '');

// ngrok 무료 주소는 브라우저 요청에 경고 페이지(HTML)를 끼워 넣습니다. 이 헤더로 건너뜁니다.
const HEADERS = { 'ngrok-skip-browser-warning': 'true' };

export type Keyframe = { time: number; time_label: string; image: string; caption: string; failed?: boolean };

export type Metrics = {
  engine: string;
  reasoning_tokens: number;
  actual_tokens: number;
  actual_input_tokens: number;
  actual_output_tokens: number;
  api_calls: number;
  baseline_tokens: number;
  baseline_frames: number;
  baseline_tokens_per_frame: number;
  saved_tokens: number;
  saved_percent: number;
  actual_cost_usd: number;
  baseline_cost_usd: number;
  saved_cost_usd: number;
  assumption: string;
};

export type Funnel = { sampled: number; stage1_kept: number; keyframes: number; duration: number };

export type JobResult = {
  summary: string;
  keyframes: Keyframe[];
  funnel: Funnel;
  metrics: Metrics;
  elapsed_sec: number;
};

export type Job = {
  status: 'queued' | 'running' | 'done' | 'error';
  stage: 1 | 2 | 3 | 4;
  stage_label: string;
  percent: number;
  message: string;
  result: JobResult | null;
  error: string | null;
};

function requireApiUrl(): string {
  if (!API_URL) throw new Error('NEXT_PUBLIC_API_URL이 설정되지 않았습니다. .env.local(로컬) 또는 Vercel 환경변수를 확인해 주세요.');
  return API_URL;
}

async function readJson<T>(res: Response): Promise<T> {
  let data: unknown;
  try {
    data = await res.json();
  } catch {
    throw new Error(`서버 응답을 읽지 못했습니다 (HTTP ${res.status}). Colab 서버가 꺼졌거나 ngrok 주소가 바뀌었을 수 있어요.`);
  }
  if (!res.ok) throw new Error((data as { error?: string })?.error ?? `요청 실패 (HTTP ${res.status})`);
  return data as T;
}

// 이전 버전 백엔드와도 동작하도록 필드는 선택 항목
export type Health = {
  status: string;
  model?: string;
  openai_key?: boolean;
  models_ready?: boolean;
  busy?: boolean;
};

export async function getHealth(): Promise<Health> {
  const res = await fetch(`${requireApiUrl()}/api/health`, { cache: 'no-store', headers: HEADERS });
  return readJson<Health>(res);
}

export async function uploadVideo(file: File): Promise<string> {
  const body = new FormData();
  body.append('video', file);
  let res: Response;
  try {
    res = await fetch(`${requireApiUrl()}/api/upload`, { method: 'POST', body, headers: HEADERS });
  } catch {
    throw new Error('백엔드에 연결하지 못했습니다. Colab 서버 셀이 실행 중인지, NEXT_PUBLIC_API_URL이 현재 ngrok 주소인지 확인해 주세요.');
  }
  return (await readJson<{ job_id: string }>(res)).job_id;
}

export async function getJob(jobId: string): Promise<Job> {
  let res: Response;
  try {
    res = await fetch(`${requireApiUrl()}/api/jobs/${encodeURIComponent(jobId)}`, { cache: 'no-store', headers: HEADERS });
  } catch {
    throw new Error('백엔드 연결이 끊겼습니다. Colab의 서버 셀이 실행 중인지 확인해 주세요.');
  }
  return readJson<Job>(res);
}
