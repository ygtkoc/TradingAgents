-- Dynamic reward/R limits and scaled take-profit planner agent.

alter table public.user_settings
  add column if not exists max_reward_r numeric not null default 5.0,
  add column if not exists min_reward_r numeric not null default 1.5;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'user_settings_max_reward_r_range'
  ) then
    alter table public.user_settings
      add constraint user_settings_max_reward_r_range
      check (max_reward_r >= 1 and max_reward_r <= 10);
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'user_settings_min_reward_r_range'
  ) then
    alter table public.user_settings
      add constraint user_settings_min_reward_r_range
      check (min_reward_r >= 0.5 and min_reward_r <= max_reward_r);
  end if;
end $$;

insert into public.agent_definitions
  (name, display_name, agent_type, category, description, enabled, can_veto, default_weight, timeout_seconds, version, tags)
values
  (
    'reward_plan_agent',
    'Reward Plan Agent',
    'RewardPlanAgent',
    'risk',
    'Builds automatic per-trade R targets and TP1/TP2/TP3 scaled exit plans.',
    true,
    true,
    1.9,
    10,
    '1.0.0',
    array['risk', 'reward', 'take-profit', 'scaled-exit']
  )
on conflict (name) do update set
  display_name = excluded.display_name,
  agent_type = excluded.agent_type,
  category = excluded.category,
  description = excluded.description,
  enabled = excluded.enabled,
  can_veto = excluded.can_veto,
  default_weight = excluded.default_weight,
  timeout_seconds = excluded.timeout_seconds,
  version = excluded.version,
  tags = excluded.tags,
  updated_at = now();
