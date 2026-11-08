import { Injectable, type OnModuleDestroy, type OnModuleInit } from '@nestjs/common';
import { PostgresSaver } from '@langchain/langgraph-checkpoint-postgres';
import { Agent, Trigger } from '@gridsense/shared/domain';
import { requireEnv } from '@gridsense/shared/server/env';
import { getServerApi } from '@gridsense/shared/server/internal-api';
import { System } from '@gridsense/shared/server/system';
import { buildGraph, Command, toThread, type AgentGraph, type ReviewAnswer } from './graph';
import type { State } from './state';

/**
 * The compiled graph, checkpointed in Postgres (schema `langgraph`, created on start), and how a hit enters it or a
 * review resumes it. After each run the thread is saved with where it stopped: paused for review, or done.
 */
@Injectable()
export class AgentGraphService implements OnModuleInit, OnModuleDestroy {

    private readonly log = System.log.withContext('AgentGraph');

    private readonly checkpointer = PostgresSaver.fromConnString(requireEnv('DATABASE_URL'), { schema: 'langgraph' });

    private graph: AgentGraph | null = null;

    public async onModuleInit(): Promise<void> {
        await this.checkpointer.setup();

        this.graph = buildGraph(this.checkpointer);

        // The graph as LangGraph draws it, for the UI.
        const drawn = await this.graph.getGraphAsync();

        await Agent.API.Internal.saveGraph(getServerApi(), {
            graph: {
                mermaid: drawn.drawMermaid(),
                nodes:   Object.keys(drawn.nodes),
            },
        });

        this.log.info('Graph ready', { nodes: Object.keys(drawn.nodes) });
    }

    /** A hit into its own thread, from the start. */
    public async handle(threadId: Agent.Thread.Id, hit: Trigger.Hit): Promise<Agent.Queue.Outcome> {
        const createdAt = new Date().toISOString();

        await Agent.API.Internal.saveThread(getServerApi(), {
            thread: toThread({ threadId, hit, createdAt, trigger: null, slots: [], decision: null, analysis: null, review: null, actions: [], steps: [] }, 'running'),
        });

        await this.require().invoke({ threadId, hit, createdAt }, this.config(threadId));

        return this.settle(threadId);
    }

    /** A paused thread, resumed with an admin's answer: `interrupt` returns it inside the review node. */
    public async resume(threadId: Agent.Thread.Id, answer: ReviewAnswer): Promise<Agent.Queue.Outcome> {
        await this.require().invoke(new Command({ resume: answer }), this.config(threadId));

        return this.settle(threadId);
    }

    /** Where the run stopped: a node still to run is the review, waiting; nothing left, the thread is done. */
    public async settle(threadId: Agent.Thread.Id): Promise<Agent.Queue.Outcome> {
        const snapshot = await this.require().getState(this.config(threadId));
        const state = snapshot.values as State;

        let status: Agent.Thread.Status = state.actions.length > 0 ? 'acted' : 'dismissed';

        if (snapshot.next.length > 0)
            status = 'awaiting-review';

        await Agent.API.Internal.saveThread(getServerApi(), { thread: toThread(state, status) });

        this.log.info('Thread', { threadId, status, decision: state.decision?.label });

        return status as Agent.Queue.Outcome;
    }

    /** A thread that threw: saved as failed, with what it had done until then. */
    public async fail(threadId: Agent.Thread.Id, error: unknown): Promise<void> {
        const snapshot = await this.require().getState(this.config(threadId));
        const state = snapshot.values as State;

        if (!state.hit)
            return;

        state.steps = [...state.steps, {
            node:    'error',
            at:      new Date(),
            summary: error instanceof Error ? error.message : String(error),
            data:    {},
        }];

        await Agent.API.Internal.saveThread(getServerApi(), { thread: toThread(state, 'failed') });
    }

    public async onModuleDestroy(): Promise<void> {
        await this.checkpointer.end();
    }

    private config(threadId: Agent.Thread.Id) {
        return { configurable: { thread_id: threadId } };
    }

    private require(): AgentGraph {
        if (this.graph === null)
            throw new Error('The graph is not built yet');

        return this.graph;
    }
}
