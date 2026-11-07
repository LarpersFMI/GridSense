-- Triggers are checked when a dataset updates, not on signals: predictions.ready → predictions, auction.published → prices.
-- data.validation-failed is gone (data_quality in the predictions carries it): its triggers go with it.
delete from gridsense.trigger where checked_on ->> 'signal' = 'data.validation-failed';

update gridsense.trigger
set checked_on = jsonb_build_object(
    'type',    'dataset',
    'dataset', case checked_on ->> 'signal' when 'predictions.ready' then 'predictions' else 'prices' end
)
where checked_on ->> 'type' = 'signal';

drop index gridsense.trigger_signal;
create index trigger_dataset on gridsense.trigger ((checked_on ->> 'dataset')) where enabled;
