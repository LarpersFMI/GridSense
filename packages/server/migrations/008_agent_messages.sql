-- The conversation on a thread (Agent.Message[]): the operator's questions and the agent's answers. Saving the thread
-- leaves it alone; a message is appended.
alter table gridsense.agent_thread add column messages jsonb not null default '[]';
