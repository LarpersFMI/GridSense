import { WorkerHost } from "@nestjs/bullmq"
import { Global, Injectable, Module, type OnModuleDestroy } from "@nestjs/common"
import { Queue, type Job, type JobsOptions } from "bullmq"
import type { Foundations } from "../domain"
import { QUEUE_PREFIX, redisConnection } from "./redis"
import { System } from "./system"

/**
 * Base for a @Processor consuming a queue declared in @gridsense/shared: Redis data is untyped, so the job
 * is parsed before `handle` sees it, and the result before BullMQ stores it. A failure is logged here.
 */
export abstract class JobProcessor<Q extends Foundations.Queue.Definition> extends WorkerHost {

    protected abstract readonly definition: Q

    protected abstract handle(job: Foundations.Queue.JobOf<Q>, raw: Job): Promise<Foundations.Queue.ResultOf<Q>>

    public async process(raw: Job): Promise<Foundations.Queue.ResultOf<Q>> {
        const log = System.log.withContext(this.definition.name)
        const startedAt = performance.now()
        const meta = {
            jobId:   raw.id,
            attempt: raw.attemptsMade + 1,
        }

        log.debug("Job received", meta)

        try {
            const job = this.definition.job.parse(raw.data) as Foundations.Queue.JobOf<Q>
            const result = this.definition.result.parse(await this.handle(job, raw)) as Foundations.Queue.ResultOf<Q>

            log.debug("Job handled", { ...meta, ms: Math.round(performance.now() - startedAt) })

            return result
        }
        catch (error) {
            log.error("Job failed", {
                ...meta,
                error: error instanceof Error ? error.message : String(error),
                ms:    Math.round(performance.now() - startedAt),
            })

            throw error
        }
    }
}

/** The only way a package enqueues: payloads are validated on the way in, against the queue's contract. */
@Injectable()
export class QueueProducer implements OnModuleDestroy {

    private readonly queues: Record<string, Queue> = {}

    public async add<Q extends Foundations.Queue.Definition>(
        definition: Q,
        data: Foundations.Queue.InputOf<Q>,
        options?: JobsOptions,
    ): Promise<Job> {
        if (!(definition.name in this.queues))
            this.queues[definition.name] = new Queue(definition.name, {
                connection:        redisConnection(),
                prefix:            QUEUE_PREFIX,
                defaultJobOptions: definition.options,
            })

        return this.queues[definition.name].add(definition.name, definition.job.parse(data), options)
    }

    public async onModuleDestroy(): Promise<void> {
        for (const queue of Object.values(this.queues))
            await queue.close()
    }
}

@Global()
@Module({
    providers: [QueueProducer],
    exports:   [QueueProducer],
})
export class QueueModule {}
