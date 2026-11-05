-- Supabase CLI 실습: 이 SQL을 migrations의 초기 마이그레이션으로 준비해 내 원격 프로젝트에 반영합니다.
-- 기존 업무 테이블을 수정하지 않습니다. 이 파일은 GitHub push로 자동 실행되지 않습니다.
begin;
create table if not exists public.hy_company_jobs (
 id text primary key, title text not null, department text not null,
 location text not null, employment text not null, experience text not null,
 summary text not null, responsibilities text[] not null default '{}',
 requirements text[] not null default '{}', tags text[] not null default '{}',
 published boolean not null default true, sort_order integer not null default 0,
 application_url text check (application_url is null or application_url ~ '^https://')
);
alter table public.hy_company_jobs enable row level security;
revoke all on table public.hy_company_jobs from anon, authenticated;
grant select on table public.hy_company_jobs to anon, authenticated;
drop policy if exists "hy_company_public_read" on public.hy_company_jobs;
create policy "hy_company_public_read" on public.hy_company_jobs
for select to anon, authenticated using (published = true);
insert into public.hy_company_jobs (id,title,department,location,employment,experience,summary,responsibilities,requirements,tags,published,sort_order,application_url) values
('product-designer','프로덕트 디자이너','디자인','서울 · 성동구','정규직','신입','사용자의 작은 불편에서 더 나은 경험을 발견해요.',ARRAY['사용자 인터뷰와 화면 흐름 설계','웹 서비스 화면 디자인과 프로토타입 제작']::text[],ARRAY['문제를 관찰하고 해결 과정을 설명할 수 있는 분','팀 프로젝트나 개인 포트폴리오가 있는 분']::text[],ARRAY['Figma','사용자 경험','프로토타입']::text[],true,1,null),
('content-marketer','콘텐츠 마케터','마케팅','서울 · 성동구','정규직','신입','우리의 이야기를 필요한 사람에게 전해요.',ARRAY['브랜드 콘텐츠 기획과 제작','채널별 반응을 살피고 콘텐츠 개선']::text[],ARRAY['글과 이미지로 생각을 전달하는 것을 좋아하는 분','콘텐츠 제작 경험을 소개할 수 있는 분']::text[],ARRAY['콘텐츠','SNS','스토리텔링']::text[],true,2,null),
('frontend-developer','프론트엔드 개발자','개발','서울 · 성동구','정규직','신입','아이디어가 실제로 동작하는 화면을 만들어요.',ARRAY['반응형 웹 화면과 사용자 기능 개발','기획·디자인 동료와 서비스 개선']::text[],ARRAY['HTML·CSS·JavaScript를 사용해 본 분','완성한 웹 프로젝트를 설명할 수 있는 분']::text[],ARRAY['React','TypeScript','웹']::text[],true,3,null),
('data-analyst','데이터 분석가','데이터','서울 · 성동구','정규직','신입','숫자 속에서 다음 선택의 힌트를 찾아요.',ARRAY['서비스 데이터 정리와 지표 분석','분석 결과를 이해하기 쉬운 화면으로 표현']::text[],ARRAY['표와 데이터를 다루는 데 관심 있는 분','분석 과정과 결과를 설명할 수 있는 분']::text[],ARRAY['SQL','Python','시각화']::text[],true,4,null),
('people-operations','피플 운영 매니저','운영','서울 · 성동구','정규직','신입','동료가 일에 집중할 수 있는 환경을 만들어요.',ARRAY['채용 일정과 지원자 경험 운영','팀 행사 기획과 업무 문서 정리']::text[],ARRAY['사람들과 협력하는 일을 좋아하는 분','일정과 문서를 꼼꼼히 관리할 수 있는 분']::text[],ARRAY['커뮤니케이션','문서 작성','기획']::text[],true,5,null),
('brand-designer','브랜드 디자이너','디자인','서울 · 성동구','정규직','신입','HY컴퍼니만의 목소리를 시각으로 표현해요.',ARRAY['브랜드 이미지와 홍보물 디자인','다양한 채널의 디자인 일관성 관리']::text[],ARRAY['시각 디자인 도구를 사용해 본 분','작업 의도를 설명할 수 있는 분']::text[],ARRAY['그래픽','브랜딩','디자인']::text[],true,6,null)
on conflict (id) do nothing;
commit;

select count(*) as published_jobs from public.hy_company_jobs where published = true;
