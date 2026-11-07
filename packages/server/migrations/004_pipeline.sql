-- The pipelines Python defines (Pipeline), each with its schedule; `available` is false once Python no longer has it.
create table gridsense.pipeline (
    name         text primary key,
    description  text not null,
    outputs      jsonb not null,
    default_cron text not null,
    available    boolean not null default true,
    cron         text not null,
    enabled      boolean not null default false,
    synced_at    timestamptz not null default now()
);

-- Their runs (Pipeline.Run), with the whole log once finished.
create table gridsense.pipeline_run (
    id            uuid primary key,
    pipeline      text not null references gridsense.pipeline (name),
    cause         text not null check (cause in ('schedule', 'manual')),
    status        text not null check (status in ('running', 'succeeded', 'failed')),
    started_at    timestamptz not null default now(),
    finished_at   timestamptz,
    rows_appended jsonb,
    error         text,
    log           text not null default ''
);

create index pipeline_run_started on gridsense.pipeline_run (started_at desc);
