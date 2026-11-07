-- A trigger on a dataset reads the rows past its watermark on an incremental column (Trigger.On.incrementalColumn):
-- issue_ts for the predictions (a run's rows), ts_utc for the prices (a cleared day's hours).
alter table gridsense.trigger add column watermark timestamptz;

update gridsense.trigger
set checked_on = checked_on || jsonb_build_object(
    'incrementalColumn', case checked_on ->> 'dataset' when 'predictions' then 'issue_ts' else 'ts_utc' end
)
where checked_on ->> 'type' = 'dataset';
