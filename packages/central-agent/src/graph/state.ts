import { Annotation } from '@langchain/langgraph';
import type { Agent, Trigger } from '@gridsense/shared/domain';

/**
 * A thread's state through the graph, checkpointed in Postgres after every node: what it read (the trigger, the
 * slots over its window), what it decided, an admin's review, what it did, and the step log.
 */
export const State = Annotation.Root({
    threadId:  Annotation<Agent.Thread.Id>,
    hit:       Annotation<Trigger.Hit>,
    createdAt: Annotation<string>,
    trigger:   Annotation<Trigger | null>({ reducer: (_, next) => next, default: () => null }),
    slots:     Annotation<Agent.Slot[]>({ reducer: (_, next) => next, default: () => [] }),
    decision:  Annotation<Agent.Decision | null>({ reducer: (_, next) => next, default: () => null }),

    // The decision's follow-ups as hits of their own, handed back to the agent once this thread has run.
    followUps: Annotation<Trigger.Hit[]>({ reducer: (_, next) => next, default: () => [] }),
    analysis:  Annotation<Agent.Analysis | null>({ reducer: (_, next) => next, default: () => null }),
    review:    Annotation<Agent.Thread.Review | null>({ reducer: (_, next) => next, default: () => null }),
    actions:   Annotation<Agent.Action[]>({ reducer: (current, next) => [...current, ...next], default: () => [] }),
    steps:     Annotation<Agent.Thread.Step[]>({ reducer: (current, next) => [...current, ...next], default: () => [] }),
});

export type State = typeof State.State;
export type Update = typeof State.Update;
