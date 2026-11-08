-- What the agent does with a trigger's hits (Trigger.Playbook).
alter table gridsense.trigger
    add column playbook text not null default 'alert'
        check (playbook in ('announce-slot', 'confirm-slot', 'cancel-slot', 'alert'));

-- One thread per hit (its id the hit's thread id): the agent's record of it — the hit, the decision, the actions,
-- and every step of the graph with what it read and decided. LangGraph's own checkpoints are in the langgraph schema.
create table gridsense.agent_thread (
    id          text primary key,
    trigger_id  uuid not null references gridsense.trigger (id) on delete cascade,
    playbook    text not null,
    status      text not null check (status in ('running', 'awaiting-review', 'acted', 'dismissed', 'failed')),
    hit         jsonb not null,
    decision    jsonb,
    actions     jsonb not null default '[]',
    steps       jsonb not null default '[]',
    review      jsonb,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index agent_thread_updated on gridsense.agent_thread (updated_at desc);
create index agent_thread_status on gridsense.agent_thread (status);

-- Zero-cost windows the agent announced, confirmed or cancelled, by window key: how a later hit on the same hours
-- finds what an earlier one did.
create table gridsense.agent_slot (
    key         text primary key,
    starts_at   timestamptz not null,
    ends_at     timestamptz not null,
    label       text not null check (label in ('confirmed', 'likely', 'possible')),
    status      text not null check (status in ('announced', 'confirmed', 'cancelled')),
    thread_ids  jsonb not null default '[]',
    reason      text not null,
    updated_at  timestamptz not null default now()
);

create index agent_slot_starts on gridsense.agent_slot (starts_at);

-- The agent's graph as LangGraph draws it (mermaid), set when the agent starts: one row.
create table gridsense.agent_graph (
    id          int primary key default 1 check (id = 1),
    mermaid     text not null,
    nodes       jsonb not null,
    updated_at  timestamptz not null default now()
);
