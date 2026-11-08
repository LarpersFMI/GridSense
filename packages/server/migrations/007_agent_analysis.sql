-- The agent's impact analysis of a thread's decision (Agent.Analysis): for the operator, or the record of why it acted alone.
alter table gridsense.agent_thread add column analysis jsonb;
