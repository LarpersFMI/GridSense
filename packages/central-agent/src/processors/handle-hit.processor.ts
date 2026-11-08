import { Processor } from '@nestjs/bullmq';
import type { Job } from 'bullmq';
import { Agent, Trigger } from '@gridsense/shared/domain';
import { JobProcessor } from '@gridsense/shared/server/queue';
import { AgentGraphService } from '../graph/agent-graph.service';

/**
 * A hit from the Watchdog into the graph, its thread id the job's id. One at a time: a later hit on the same window
 * (a confirmation, a cancellation) must find what an earlier one announced.
 */
@Processor(Agent.Queue.HandleHit.Definition.name, { concurrency: 1 })
export class HandleHitProcessor extends JobProcessor<typeof Agent.Queue.HandleHit.Definition> {

    protected readonly definition = Agent.Queue.HandleHit.Definition;

    constructor(private readonly agent: AgentGraphService) {
        super();
    }

    protected async handle(hit: Trigger.Hit, raw: Job): Promise<Agent.Queue.Result> {
        const threadId = Agent.Thread.Id.parse(raw.id ?? Trigger.Hit.getThreadId(hit));

        try {
            return { outcome: await this.agent.handle(threadId, hit) };
        }
        catch (error) {
            await this.agent.fail(threadId, error);

            throw error;
        }
    }
}
