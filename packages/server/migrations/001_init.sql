create schema if not exists gridsense;

-- The Forecaster's runs, as the Python pipeline reports them (Forecaster.Run).
create table gridsense.run (
    id               uuid primary key,
    issue_ts         timestamptz not null unique,
    model_version    text not null,
    row_count        integer not null check (row_count > 0),
    predictions_path text not null,
    reported_at      timestamptz not null default now()
);

-- The admin's triggers (Trigger). The jsonb columns hold the zod-validated shapes as they are.
create table gridsense.trigger (
    id               uuid primary key,
    name             text not null,
    description      text not null,
    enabled          boolean not null,
    checked_on       jsonb not null,
    match_mode       text not null check (match_mode in ('all', 'any')),
    conditions       jsonb not null,
    hit_grouping     jsonb not null,
    cooldown_minutes integer not null check (cooldown_minutes >= 0),
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);

create index trigger_signal on gridsense.trigger ((checked_on ->> 'signal')) where enabled;
