-- MAZE GAME online backend (Supabase / PostgreSQL).
-- Security model: clients never write tables directly. Every write goes through a SECURITY DEFINER
-- function that checks auth.uid() and validates the input. Tables are protected with RLS as well.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------- tables
create table if not exists public.profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  username    text not null check (username ~ '^[A-Za-z0-9_]{3,20}$'),
  created_at  timestamptz not null default now()
);
create unique index if not exists profiles_username_lower_idx on public.profiles (lower(username));

create table if not exists public.player_progress (
  user_id     uuid primary key references auth.users(id) on delete cascade,
  data        jsonb not null,
  xp          integer not null default 0 check (xp >= 0),
  version     integer not null default 1,
  updated_at  timestamptz not null default now()
);

create table if not exists public.daily_challenges (
  day              date primary key,
  seed             bigint not null,
  algorithm        text not null,
  width            integer not null check (width between 4 and 64),
  height           integer not null check (height between 4 and 64),
  start_cell       jsonb not null,          -- [x, y]
  exit_cell        jsonb not null,          -- [x, y]
  walls            jsonb not null,          -- rows of wall bitmasks: N=1 E=2 S=4 W=8
  created_at       timestamptz not null default now()
);

create table if not exists public.challenge_runs (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users(id) on delete cascade,
  day           date not null references public.daily_challenges(day),
  started_at    timestamptz not null default now(),   -- the SERVER clock decides the time
  submitted_at  timestamptz,
  elapsed_ms    integer,
  accepted      boolean,
  reject_reason text
);
create index if not exists challenge_runs_user_day_idx on public.challenge_runs (user_id, day);

create table if not exists public.leaderboard_entries (
  user_id      uuid not null references auth.users(id) on delete cascade,
  day          date not null references public.daily_challenges(day),
  elapsed_ms   integer not null check (elapsed_ms > 0),
  path_length  integer not null,
  created_at   timestamptz not null default now(),
  primary key (user_id, day)
);
create index if not exists leaderboard_day_time_idx on public.leaderboard_entries (day, elapsed_ms);

-- ---------------------------------------------------------------- RLS + privileges
alter table public.profiles            enable row level security;
alter table public.player_progress     enable row level security;
alter table public.daily_challenges    enable row level security;
alter table public.challenge_runs      enable row level security;
alter table public.leaderboard_entries enable row level security;

revoke all on public.profiles, public.player_progress, public.daily_challenges,
              public.challenge_runs, public.leaderboard_entries from anon, authenticated;

-- Players may only READ their own rows. No insert/update/delete policies exist => writes are denied.
grant select on public.profiles, public.player_progress, public.challenge_runs to authenticated;
create policy profiles_select_own  on public.profiles        for select to authenticated using (id = auth.uid());
create policy progress_select_own  on public.player_progress for select to authenticated using (user_id = auth.uid());
create policy runs_select_own      on public.challenge_runs   for select to authenticated using (user_id = auth.uid());
-- daily_challenges and leaderboard_entries have NO client policy: the maze is only handed out by
-- start_daily_run() (which starts the clock) and the board is only readable through get_daily_leaderboard().

grant all on public.daily_challenges to service_role;   -- the publisher script runs with the service key

-- ---------------------------------------------------------------- private helper
-- Replays a path against the stored walls. Returns NULL when valid, otherwise a reason code.
create or replace function public.validate_maze_path(
  p_walls jsonb, p_w int, p_h int, p_start jsonb, p_exit jsonb, p_path jsonb
) returns text
language plpgsql immutable
set search_path = public
as $$
declare
  n int; i int; x int; y int; px int; py int; dx int; dy int; bit int;
  seen int[] := '{}';
  cell jsonb;
begin
  if p_path is null or jsonb_typeof(p_path) <> 'array' then return 'bad_path'; end if;
  n := jsonb_array_length(p_path);
  if n < 2 or n > p_w * p_h then return 'bad_length'; end if;
  for i in 0 .. n - 1 loop
    cell := p_path -> i;
    if jsonb_typeof(cell) <> 'array' or jsonb_array_length(cell) <> 2
       or jsonb_typeof(cell -> 0) <> 'number' or jsonb_typeof(cell -> 1) <> 'number' then
      return 'bad_cell';
    end if;
    x := (cell ->> 0)::numeric::int; y := (cell ->> 1)::numeric::int;
    if x < 0 or y < 0 or x >= p_w or y >= p_h then return 'out_of_bounds'; end if;
    if i = 0 then
      if x <> (p_start ->> 0)::int or y <> (p_start ->> 1)::int then return 'bad_start'; end if;
    else
      dx := x - px; dy := y - py;
      if abs(dx) + abs(dy) <> 1 then return 'not_adjacent'; end if;
      bit := case when dx = 1 then 2 when dx = -1 then 8 when dy = 1 then 4 else 1 end;
      if (((p_walls -> py) ->> px)::int & bit) <> 0 then return 'wall_crossed'; end if;
      if (y * p_w + x) = any(seen) then return 'self_crossing'; end if;
    end if;
    seen := seen || (y * p_w + x);
    px := x; py := y;
  end loop;
  if px <> (p_exit ->> 0)::int or py <> (p_exit ->> 1)::int then return 'exit_not_reached'; end if;
  return null;
end $$;
revoke all on function public.validate_maze_path(jsonb, int, int, jsonb, jsonb, jsonb) from public, anon, authenticated;

-- ---------------------------------------------------------------- profile
create or replace function public.create_profile(p_username text) returns void
language plpgsql security definer set search_path = public
as $$
begin
  if auth.uid() is null then raise exception 'not_authenticated'; end if;
  if p_username is null or p_username !~ '^[A-Za-z0-9_]{3,20}$' then raise exception 'invalid_username'; end if;
  begin
    insert into public.profiles (id, username) values (auth.uid(), p_username);
  exception when unique_violation then
    if exists (select 1 from public.profiles where id = auth.uid()) then raise exception 'profile_exists'; end if;
    raise exception 'username_taken';
  end;
end $$;

create or replace function public.get_my_profile() returns json
language sql security definer stable set search_path = public
as $$ select json_build_object('id', id, 'username', username) from public.profiles where id = auth.uid() $$;

-- ---------------------------------------------------------------- cloud save (optimistic concurrency)
create or replace function public.load_progress() returns json
language sql security definer stable set search_path = public
as $$ select json_build_object('data', data, 'version', version, 'xp', xp, 'updated_at', updated_at)
      from public.player_progress where user_id = auth.uid() $$;

create or replace function public.save_progress(p_data jsonb, p_expected_version int) returns integer
language plpgsql security definer set search_path = public
as $$
declare cur int; old_xp int; new_xp int;
begin
  if auth.uid() is null then raise exception 'not_authenticated'; end if;
  if p_data is null or jsonb_typeof(p_data) <> 'object' then raise exception 'invalid_data'; end if;
  if length(p_data::text) > 200000 then raise exception 'data_too_large'; end if;
  begin
    new_xp := (p_data ->> 'xp')::int;
  exception when others then raise exception 'invalid_data'; end;
  if new_xp is null or new_xp < 0 then raise exception 'invalid_data'; end if;

  select version, xp into cur, old_xp from public.player_progress where user_id = auth.uid() for update;
  if not found then
    insert into public.player_progress (user_id, data, xp, version) values (auth.uid(), p_data, new_xp, 1);
    return 1;
  end if;
  if p_expected_version is distinct from cur then raise exception 'version_conflict'; end if;
  -- XP only ever grows: a lower value means a stale or tampered copy and must never replace the stored one
  if new_xp < old_xp then raise exception 'xp_regression'; end if;
  update public.player_progress
     set data = p_data, xp = new_xp, version = cur + 1, updated_at = now()
   where user_id = auth.uid();
  return cur + 1;
end $$;

-- ---------------------------------------------------------------- daily challenge
create or replace function public.start_daily_run() returns json
language plpgsql security definer set search_path = public
as $$
declare today date := (now() at time zone 'utc')::date; c public.daily_challenges; rid uuid; recent int;
begin
  if auth.uid() is null then raise exception 'not_authenticated'; end if;
  if not exists (select 1 from public.profiles where id = auth.uid()) then raise exception 'profile_required'; end if;
  select * into c from public.daily_challenges where day = today;
  if not found then raise exception 'no_challenge_today'; end if;
  select count(*) into recent from public.challenge_runs where user_id = auth.uid() and day = today;
  if recent >= 30 then raise exception 'too_many_attempts'; end if;   -- simple rate limit
  insert into public.challenge_runs (user_id, day) values (auth.uid(), today) returning id into rid;
  return json_build_object('run_id', rid, 'day', today, 'width', c.width, 'height', c.height,
                           'start', c.start_cell, 'exit', c.exit_cell, 'walls', c.walls);
end $$;

create or replace function public.submit_daily_run(p_run_id uuid, p_path jsonb) returns json
language plpgsql security definer set search_path = public
as $$
declare
  r public.challenge_runs; c public.daily_challenges; elapsed int; reason text; n int; my_rank int; best int;
begin
  if auth.uid() is null then raise exception 'not_authenticated'; end if;
  select * into r from public.challenge_runs where id = p_run_id and user_id = auth.uid() for update;
  if not found then raise exception 'run_not_found'; end if;
  if r.submitted_at is not null then raise exception 'already_submitted'; end if;
  select * into c from public.daily_challenges where day = r.day;

  elapsed := least(2147483647, floor(extract(epoch from (now() - r.started_at)) * 1000))::int;
  reason := public.validate_maze_path(c.walls, c.width, c.height, c.start_cell, c.exit_cell, p_path);
  n := case when jsonb_typeof(p_path) = 'array' then jsonb_array_length(p_path) else 0 end;
  if reason is null and elapsed > 3600000 then reason := 'run_expired'; end if;
  -- humanly impossible times (scripted submissions): at least 80 ms per cell and 1.5 s overall
  if reason is null and elapsed < greatest(1500, n * 80) then reason := 'too_fast'; end if;

  update public.challenge_runs
     set submitted_at = now(), elapsed_ms = elapsed, accepted = (reason is null), reject_reason = reason
   where id = r.id;
  if reason is not null then
    return json_build_object('accepted', false, 'reason', reason, 'elapsed_ms', elapsed);
  end if;

  insert into public.leaderboard_entries (user_id, day, elapsed_ms, path_length)
  values (auth.uid(), r.day, elapsed, n)
  on conflict (user_id, day) do update
     set elapsed_ms = excluded.elapsed_ms, path_length = excluded.path_length, created_at = now()
   where excluded.elapsed_ms < public.leaderboard_entries.elapsed_ms;      -- only improvements count
  select elapsed_ms into best from public.leaderboard_entries where user_id = auth.uid() and day = r.day;
  select count(*) + 1 into my_rank from public.leaderboard_entries where day = r.day and elapsed_ms < best;
  return json_build_object('accepted', true, 'elapsed_ms', elapsed, 'best_ms', best, 'rank', my_rank);
end $$;

create or replace function public.get_daily_leaderboard(p_day date default null, p_limit int default 50) returns json
language sql security definer stable set search_path = public
as $$
  with d as (select coalesce(p_day, (now() at time zone 'utc')::date) as day),
  ranked as (
    select rank() over (order by l.elapsed_ms, l.created_at) as rank, p.username, l.elapsed_ms,
           (l.user_id = auth.uid()) as is_me
      from public.leaderboard_entries l join public.profiles p on p.id = l.user_id, d
     where l.day = d.day
  )
  select coalesce(json_agg(r order by r.rank), '[]'::json)
    from (select * from ranked where rank <= least(greatest(p_limit, 1), 100) or is_me) r
$$;

-- ---------------------------------------------------------------- who may call what
revoke all on function public.create_profile(text), public.get_my_profile(), public.load_progress(),
  public.save_progress(jsonb, int), public.start_daily_run(), public.submit_daily_run(uuid, jsonb),
  public.get_daily_leaderboard(date, int) from public, anon, authenticated;
grant execute on function public.create_profile(text), public.get_my_profile(), public.load_progress(),
  public.save_progress(jsonb, int), public.start_daily_run(), public.submit_daily_run(uuid, jsonb),
  public.get_daily_leaderboard(date, int) to authenticated;
grant execute on function public.get_daily_leaderboard(date, int) to anon;   -- the board is public
