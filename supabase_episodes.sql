-- ============================================================
-- EBS 다큐프라임 챗봇 - episodes 테이블 (회차/부제 정보)
-- Supabase SQL Editor에서 실행하세요
-- ============================================================

-- 1. episodes 테이블
create table if not exists public.episodes (
  id             bigint generated always as identity primary key,
  step_id        text not null,                    -- contents.step_id 참조
  lect_id        text unique not null,             -- 회차 고유 ID
  episode_title  text not null default '',         -- 예: "백세부자 2부"
  description    text default '',
  date           text default '',
  views          text default '',
  likes          text default '',
  thumbnail      text default '',
  url            text default '',
  created_at     timestamptz default now(),
  updated_at     timestamptz default now(),

  constraint fk_episodes_step_id
    foreign key (step_id) references public.contents(step_id)
    on delete cascade
);

-- updated_at 자동 갱신 (contents와 동일 함수 재사용)
create trigger episodes_updated_at
  before update on public.episodes
  for each row execute function update_updated_at();

-- 인덱스
create index if not exists episodes_step_id_idx on public.episodes (step_id);
create index if not exists episodes_date_idx    on public.episodes (date desc);

-- 2. RLS
alter table public.episodes enable row level security;

drop policy if exists "public_read_episodes" on public.episodes;
create policy "public_read_episodes"
  on public.episodes for select using (true);

-- 3. 편의 뷰: contents + 회차 수 조합
create or replace view public.contents_with_episode_count as
select
  c.*,
  count(e.lect_id) as episode_count
from public.contents c
left join public.episodes e using (step_id)
group by c.id;
