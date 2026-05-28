-- ============================================================
-- EBS 다큐프라임 챗봇 - Supabase 테이블 설정
-- Supabase SQL Editor에서 실행하세요
-- ============================================================

-- 1. contents 테이블 (EBS 다큐프라임 메타데이터)
create table if not exists public.contents (
  id          bigint generated always as identity primary key,
  step_id     text unique not null,
  title       text not null,
  description text default '',
  date        text default '',
  category    text default '',
  views       text default '',
  likes       text default '',
  thumbnail   text default '',
  url         text default '',
  created_at  timestamptz default now(),
  updated_at  timestamptz default now()
);

-- 업데이트 시 updated_at 자동 갱신
create or replace function update_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger contents_updated_at
  before update on public.contents
  for each row execute function update_updated_at();

-- 검색 성능을 위한 인덱스
create index if not exists contents_date_idx      on public.contents (date desc);
create index if not exists contents_category_idx  on public.contents (category);
create index if not exists contents_title_idx     on public.contents using gin(to_tsvector('simple', title));
create index if not exists contents_desc_idx      on public.contents using gin(to_tsvector('simple', description));


-- 2. search_logs 테이블 (검색 이력 로그)
create table if not exists public.search_logs (
  id            bigint generated always as identity primary key,
  query         text not null,
  result_count  int  default 0,
  top_results   jsonb default '[]',   -- 상위 3개 결과 스냅샷
  session_id    text default '',      -- 브라우저 세션 식별자
  created_at    timestamptz default now()
);

create index if not exists search_logs_created_at_idx  on public.search_logs (created_at desc);
create index if not exists search_logs_query_idx       on public.search_logs (query);
create index if not exists search_logs_session_idx     on public.search_logs (session_id);


-- ============================================================
-- 3. Row Level Security (RLS)
-- ============================================================
alter table public.contents    enable row level security;
alter table public.search_logs enable row level security;

-- contents: 누구나 읽기 가능 (anon key)
drop policy if exists "public_read_contents" on public.contents;
create policy "public_read_contents"
  on public.contents for select
  using (true);

-- search_logs: 누구나 INSERT 가능, 읽기는 service_role만
drop policy if exists "public_insert_search_logs" on public.search_logs;
create policy "public_insert_search_logs"
  on public.search_logs for insert
  with check (true);


-- ============================================================
-- 4. 유용한 분석 뷰 (대시보드용)
-- ============================================================

-- 일별 검색량
create or replace view public.daily_search_stats as
select
  date_trunc('day', created_at) as day,
  count(*)                      as search_count,
  count(distinct session_id)    as unique_sessions,
  avg(result_count)             as avg_results
from public.search_logs
group by 1
order by 1 desc;

-- 인기 검색어 TOP 50
create or replace view public.top_queries as
select
  query,
  count(*)       as search_count,
  avg(result_count) as avg_results,
  max(created_at)   as last_searched
from public.search_logs
group by query
order by search_count desc
limit 50;

-- 검색어 없음 비율 (개선 필요 쿼리 찾기)
create or replace view public.zero_result_queries as
select
  query,
  count(*) as search_count,
  max(created_at) as last_searched
from public.search_logs
where result_count = 0
group by query
order by search_count desc;
