begin;

grant select, insert, update on table public.paper_accounts to authenticated;
grant select on table public.paper_account_events to authenticated;

drop policy if exists paper_accounts_self_insert on public.paper_accounts;
create policy paper_accounts_self_insert
    on public.paper_accounts
    for insert
    with check (auth.uid() = user_id);

drop policy if exists paper_accounts_self_update on public.paper_accounts;
create policy paper_accounts_self_update
    on public.paper_accounts
    for update
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

commit;
