import { Injectable, type OnModuleDestroy } from '@nestjs/common';
import { Queue } from 'bullmq';
import { Agent, Foundations, Trigger } from '@gridsense/shared/domain';
import { QUEUE_PREFIX, redisConnection } from '@gridsense/shared/server/redis';

/**
 * The hits the Watchdog raised, read from the agent's queue (`agent.handle-hit`), where they wait for the agent.
 * The queue keeps the last 1000 completed and failed jobs; nothing else stores hits.
 */
@Injectable()
export class HitService implements OnModuleDestroy {

    private readonly queue = new Queue(Agent.Queue.HandleHit.Definition.name, {
        connection: redisConnection(),
        prefix:     QUEUE_PREFIX,
    });

    /** The latest hits, newest first, by thread id — one trigger's if `triggerId` is given. */
    public async list(query: Trigger.API.ListHits.Query): Promise<Record<Foundations.Thread.Id, Trigger.Hit.Queued>> {
        const hits: Record<Foundations.Thread.Id, Trigger.Hit.Queued> = {};

        for (const status of Trigger.Hit.Queued.Status.options) {
            for (const job of await this.queue.getJobs([status], 0, query.limit - 1, false)) {
                const hit = Trigger.Hit.Schema.parse(job.data);
                const threadId = Trigger.Hit.getThreadId(hit);

                if (query.triggerId !== undefined && hit.triggerId !== query.triggerId)
                    continue;

                hits[threadId] = {
                    threadId,
                    hit,
                    raisedAt: new Date(job.timestamp),
                    status,
                };
            }
        }

        const newest = Object.values(hits);

        newest.sort((a, b) => b.raisedAt.getTime() - a.raisedAt.getTime());

        const latest: Record<Foundations.Thread.Id, Trigger.Hit.Queued> = {};

        for (const queued of newest.slice(0, query.limit))
            latest[queued.threadId] = queued;

        return latest;
    }

    public async onModuleDestroy(): Promise<void> {
        await this.queue.close();
    }
}
