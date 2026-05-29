-- Hotfix: refresh manual_trade_action against the current trades schema.
-- Paper/shadow positions can be closed, reduced, and increased from the UI.
-- Live positions are limited to local protective level updates; real exchange
-- orders must still go through audited server-side execution.

create or replace function public.manual_trade_action(
  p_trade_id uuid,
  p_action text,
  p_quantity numeric default null,
  p_percent numeric default null,
  p_price numeric default null,
  p_stop_loss numeric default null,
  p_take_profit numeric default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_trade public.trades%rowtype;
  v_user uuid := auth.uid();
  v_action text := lower(trim(coalesce(p_action, '')));
  v_qty numeric;
  v_price numeric;
  v_entry numeric;
  v_current_qty numeric;
  v_close_qty numeric;
  v_remaining_qty numeric;
  v_realized numeric := 0;
  v_total_realized numeric := 0;
  v_new_avg numeric;
  v_new_notional numeric;
  v_new_risk numeric;
  v_new_expected numeric;
  v_reserved numeric;
  v_released numeric := 0;
  v_additional_reserve numeric := 0;
  v_now timestamptz := now();
  v_acct record;
begin
  if v_user is null then
    raise exception 'manual_trade_action: authentication required';
  end if;

  select * into v_trade
  from public.trades
  where id = p_trade_id
    and user_id = v_user
  for update;

  if not found then
    raise exception 'manual_trade_action: trade not found';
  end if;

  if v_trade.status <> 'open' then
    raise exception 'manual_trade_action: trade is not open';
  end if;

  v_current_qty := coalesce(nullif(v_trade.filled_quantity, 0), v_trade.quantity, 0);
  v_entry := coalesce(nullif(v_trade.avg_entry_price, 0), v_trade.entry_price);
  v_reserved := coalesce(nullif((v_trade.metadata ->> 'reserved_amount')::numeric, 0), nullif(v_trade.risk_amount, 0), 0);

  select close_price into v_price
  from public.market_snapshots
  where exchange = v_trade.exchange
    and symbol = v_trade.symbol
    and timeframe = '1m'
  order by captured_at desc
  limit 1;
  v_price := coalesce(nullif(p_price, 0), nullif(v_price, 0), v_entry);

  if v_action in ('set_stop_loss', 'move_stop_to_entry') then
    update public.trades
    set stop_loss = case when v_action = 'move_stop_to_entry' then v_entry else p_stop_loss end,
        lifecycle_status = 'idle',
        lifecycle_error = null,
        lifecycle_retry_count = 0,
        updated_at = v_now
    where id = v_trade.id;

    insert into public.trade_events(trade_id, trade_decision_id, bot_id, user_id, event_type, details)
    values (
      v_trade.id, v_trade.trade_decision_id, v_trade.bot_id, v_trade.user_id,
      'manual_stop_updated',
      jsonb_build_object('action', v_action, 'stop_loss', case when v_action = 'move_stop_to_entry' then v_entry else p_stop_loss end)
    );
    return jsonb_build_object('ok', true, 'action', v_action, 'trade_id', v_trade.id);
  end if;

  if v_action = 'set_take_profit' then
    update public.trades
    set take_profit = p_take_profit,
        lifecycle_status = 'idle',
        lifecycle_error = null,
        lifecycle_retry_count = 0,
        updated_at = v_now
    where id = v_trade.id;

    insert into public.trade_events(trade_id, trade_decision_id, bot_id, user_id, event_type, details)
    values (
      v_trade.id, v_trade.trade_decision_id, v_trade.bot_id, v_trade.user_id,
      'manual_take_profit_updated',
      jsonb_build_object('take_profit', p_take_profit)
    );
    return jsonb_build_object('ok', true, 'action', v_action, 'trade_id', v_trade.id);
  end if;

  if v_trade.mode not in ('paper', 'shadow') then
    raise exception 'manual_trade_action: live close/add/reduce requires server exchange execution';
  end if;

  if v_current_qty <= 0 or v_entry <= 0 or v_price <= 0 then
    raise exception 'manual_trade_action: invalid trade quantity or price';
  end if;

  if v_action in ('add_quantity', 'buy', 'sell') then
    v_qty := coalesce(nullif(p_quantity, 0), 0);
    if v_qty <= 0 then
      raise exception 'manual_trade_action: quantity is required';
    end if;

    if (v_action = 'buy' and v_trade.direction = 'short') or (v_action = 'sell' and v_trade.direction = 'long') then
      v_action := 'reduce_quantity';
    else
      v_new_avg := ((v_entry * v_current_qty) + (v_price * v_qty)) / (v_current_qty + v_qty);
      v_new_notional := v_new_avg * (v_current_qty + v_qty);
      v_new_risk := case
        when v_trade.stop_loss is not null then abs(v_new_avg - v_trade.stop_loss) * (v_current_qty + v_qty)
        else v_trade.risk_amount
      end;
      v_new_expected := case
        when v_new_risk is not null and v_trade.risk_reward_ratio is not null then v_new_risk * v_trade.risk_reward_ratio
        else v_trade.expected_reward
      end;
      v_additional_reserve := case
        when v_trade.stop_loss is not null then abs(v_price - v_trade.stop_loss) * v_qty
        else v_price * v_qty
      end;
      v_additional_reserve := least(greatest(v_additional_reserve, 0), v_price * v_qty);

      select * into v_acct
      from public.paper_accounts
      where user_id = v_trade.user_id
      for update;

      if v_trade.mode = 'paper' and not found then
        raise exception 'manual_trade_action: paper account not found';
      end if;

      if found and coalesce(v_acct.available_balance, v_acct.balance - v_acct.reserved_balance, 0) < v_additional_reserve then
        raise exception 'manual_trade_action: insufficient paper balance for add';
      end if;

      if found then
        update public.paper_accounts
        set reserved_balance = coalesce(reserved_balance, 0) + v_additional_reserve
        where id = v_acct.id;

        insert into public.paper_account_events(
          account_id, user_id, trade_id, event_type, delta, realized_delta,
          unrealized_delta, balance_after, realized_after, unrealized_after, note, metadata
        )
        values (
          v_acct.id, v_trade.user_id, v_trade.id, 'manual_trade_reserve',
          0, 0, 0,
          coalesce(v_acct.balance, 0),
          coalesce(v_acct.realized_pnl, 0),
          coalesce(v_acct.unrealized_pnl, 0),
          'manual add ' || v_trade.symbol,
          jsonb_build_object(
            'action', v_action,
            'price', v_price,
            'quantity', v_qty,
            'reserve_amount', v_additional_reserve,
            'reserved_before', coalesce(v_acct.reserved_balance, 0),
            'reserved_after', coalesce(v_acct.reserved_balance, 0) + v_additional_reserve,
            'available_after', coalesce(v_acct.balance, 0) - (coalesce(v_acct.reserved_balance, 0) + v_additional_reserve)
          )
        );
      end if;

      update public.trades
      set quantity = v_current_qty + v_qty,
          filled_quantity = v_current_qty + v_qty,
          avg_entry_price = v_new_avg,
          notional = v_new_notional,
          risk_amount = v_new_risk,
          expected_reward = v_new_expected,
          lifecycle_status = 'idle',
          lifecycle_error = null,
          lifecycle_retry_count = 0,
          metadata = coalesce(metadata, '{}'::jsonb) || jsonb_build_object(
            'manual_last_action', 'add_quantity',
            'manual_last_quantity', v_qty,
            'manual_last_price', v_price,
            'reserved_amount', v_reserved + v_additional_reserve
          ),
          updated_at = v_now
      where id = v_trade.id;

      insert into public.trade_events(trade_id, trade_decision_id, bot_id, user_id, event_type, details)
      values (
        v_trade.id, v_trade.trade_decision_id, v_trade.bot_id, v_trade.user_id,
        'manual_position_added',
        jsonb_build_object('quantity', v_qty, 'price', v_price, 'new_quantity', v_current_qty + v_qty)
      );
      return jsonb_build_object('ok', true, 'action', 'add_quantity', 'trade_id', v_trade.id);
    end if;
  end if;

  if v_action in ('reduce_quantity', 'close_percent', 'close_full') then
    if v_action = 'close_full' then
      v_close_qty := v_current_qty;
    elsif p_percent is not null and p_percent > 0 then
      v_close_qty := v_current_qty * least(p_percent, 100) / 100;
    else
      v_close_qty := coalesce(nullif(p_quantity, 0), 0);
    end if;

    if v_close_qty <= 0 then
      raise exception 'manual_trade_action: close quantity is required';
    end if;
    if v_close_qty > v_current_qty then
      v_close_qty := v_current_qty;
    end if;

    v_remaining_qty := greatest(v_current_qty - v_close_qty, 0);
    v_realized := case
      when v_trade.direction = 'short' then (v_entry - v_price) * v_close_qty
      else (v_price - v_entry) * v_close_qty
    end;
    v_total_realized := coalesce(v_trade.realized_pnl, 0) + v_realized;
    v_released := case
      when v_current_qty > 0 then least(v_reserved, greatest(0, v_reserved * (v_close_qty / v_current_qty)))
      else 0
    end;

    if v_remaining_qty <= 0.00000001 then
      update public.trades
      set status = 'closed',
          lifecycle_status = 'closed',
          lifecycle_worker_id = null,
          lifecycle_claimed_at = null,
          exit_price = v_price,
          avg_exit_price = v_price,
          closed_at = v_now,
          realized_pnl = v_total_realized,
          unrealized_pnl = null,
          close_reason = 'manual',
          pnl_pct = case when v_entry * v_current_qty > 0 then (v_total_realized / (v_entry * v_current_qty)) * 100 else null end,
          r_multiple = case when v_trade.risk_amount is not null and v_trade.risk_amount > 0 then v_total_realized / v_trade.risk_amount else null end,
          metadata = coalesce(metadata, '{}'::jsonb) || jsonb_build_object(
            'manual_last_action', 'close_full',
            'manual_last_quantity', v_close_qty,
            'manual_last_price', v_price,
            'reserved_amount', 0,
            'reserved_released', coalesce((metadata ->> 'reserved_released')::numeric, 0) + v_released
          ),
          updated_at = v_now
      where id = v_trade.id;
    else
      update public.trades
      set filled_quantity = v_remaining_qty,
          realized_pnl = v_total_realized,
          unrealized_pnl = null,
          lifecycle_status = 'idle',
          lifecycle_error = null,
          lifecycle_retry_count = 0,
          metadata = coalesce(metadata, '{}'::jsonb) || jsonb_build_object(
            'manual_last_action', 'reduce_quantity',
            'manual_last_quantity', v_close_qty,
            'manual_last_price', v_price,
            'reserved_amount', greatest(0, v_reserved - v_released),
            'reserved_released', coalesce((metadata ->> 'reserved_released')::numeric, 0) + v_released
          ),
          updated_at = v_now
      where id = v_trade.id;
    end if;

    select * into v_acct
    from public.paper_accounts
    where user_id = v_trade.user_id
    for update;

    if found then
      update public.paper_accounts
      set balance = coalesce(balance, 0) + v_realized,
          reserved_balance = greatest(0, coalesce(reserved_balance, 0) - v_released),
          realized_pnl = coalesce(realized_pnl, 0) + v_realized
      where id = v_acct.id;

      insert into public.paper_account_events(
        account_id, user_id, trade_id, event_type, delta, realized_delta,
        unrealized_delta, balance_after, realized_after, unrealized_after, note, metadata
      )
      values (
        v_acct.id, v_trade.user_id, v_trade.id, 'manual_trade_action',
        v_realized, v_realized, 0,
        coalesce(v_acct.balance, 0) + v_realized,
        coalesce(v_acct.realized_pnl, 0) + v_realized,
        coalesce(v_acct.unrealized_pnl, 0),
        'manual ' || v_action || ' ' || v_trade.symbol,
        jsonb_build_object('action', v_action, 'price', v_price, 'quantity', v_close_qty)
        || jsonb_build_object(
          'reserved_released', v_released,
          'reserved_before', coalesce(v_acct.reserved_balance, 0),
          'reserved_after', greatest(0, coalesce(v_acct.reserved_balance, 0) - v_released),
          'available_after', coalesce(v_acct.balance, 0) + v_realized - greatest(0, coalesce(v_acct.reserved_balance, 0) - v_released)
        )
      );
    end if;

    insert into public.trade_events(trade_id, trade_decision_id, bot_id, user_id, event_type, details)
    values (
      v_trade.id, v_trade.trade_decision_id, v_trade.bot_id, v_trade.user_id,
      case when v_remaining_qty <= 0.00000001 then 'manual_close' else 'manual_reduce' end,
      jsonb_build_object(
        'action', v_action,
        'quantity', v_close_qty,
        'remaining_quantity', v_remaining_qty,
        'price', v_price,
        'realized_pnl', v_realized
      )
    );

    return jsonb_build_object(
      'ok', true,
      'action', v_action,
      'trade_id', v_trade.id,
      'closed_quantity', v_close_qty,
      'remaining_quantity', v_remaining_qty,
      'realized_pnl', v_realized
    );
  end if;

  raise exception 'manual_trade_action: unknown action %', p_action;
end;
$$;

revoke all on function public.manual_trade_action(uuid, text, numeric, numeric, numeric, numeric, numeric) from public;
grant execute on function public.manual_trade_action(uuid, text, numeric, numeric, numeric, numeric, numeric) to authenticated;

-- Make the new RPC visible to PostgREST/Supabase REST immediately after deploy.
notify pgrst, 'reload schema';
