export type Job = {
 id: string; title: string; department: string; location: string; employment: string;
 experience: string; summary: string; responsibilities: string[]; requirements: string[];
 tags: string[]; published: boolean; sort_order: number; application_url: string | null;
};
export type JobResult = { jobs: Job[]; source: 'sample' | 'supabase' | 'error'; message?: string };
