-- The replay (Replay): the trained models run day by day over a past period. One row: where it starts, set from the UI.
create table gridsense.replay (
    id         boolean primary key default true check (id),
    start      date not null,
    updated_at timestamptz not null default now()
);

insert into gridsense.replay (start) values ('2025-04-24');
