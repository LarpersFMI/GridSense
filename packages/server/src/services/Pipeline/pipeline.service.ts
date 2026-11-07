import { BadRequestException, Injectable, type OnModuleDestroy } from '@nestjs/common';
import { Queue } from 'bullmq';
import { Pipeline, PipelineRunner } from '@gridsense/shared/domain';
import { QueueProducer } from '@gridsense/shared/server/queue';
import { RealtimeService } from '@gridsense/shared/server/realtime';
import { QUEUE_PREFIX, redisConnection } from '@gridsense/shared/server/redis';
import { PipelineDB, PipelineRepository } from './pipeline.repository';

/**
 * Pipelines: their definitions (from Python, through the PipelineRunner), their schedules (from the UI) and their
 * runs. A schedule change reconciles the PipelineRunner's job schedulers; a run's start and end go out live.
 */
@Injectable()
export class PipelineService implements OnModuleDestroy {

    // Read only: the PipelineRunner's job schedulers, for when each schedule fires next.
    private readonly runQueue = new Queue(PipelineRunner.Queue.RunPipeline.Definition.name, {
        connection: redisConnection(),
        prefix:     QUEUE_PREFIX,
    });

    constructor(
        private readonly pipelines: PipelineRepository,
        private readonly queues: QueueProducer,
        private readonly realtime: RealtimeService,
    ) {}

    public async sync(definitions: Pipeline[]): Promise<Record<Pipeline.Name, Pipeline>> {
        await this.pipelines.sync(definitions);
        await this.queues.add(PipelineRunner.Queue.Reconcile.Definition, {});

        const synced: Record<Pipeline.Name, Pipeline> = {};

        for (const definition of definitions)
            synced[definition.name] = definition;

        return synced;
    }

    public async list(): Promise<Pipeline.API.List.Response> {
        const response: Pipeline.API.List.Response = {
            pipelines: {},
            schedules: {},
            lastRuns:  await this.pipelines.listLastRuns(),
            nextRuns:  {},
        };

        // A scheduler's key is its pipeline's name (the PipelineRunner's ReconcileProcessor).
        for (const scheduler of await this.runQueue.getJobSchedulers())
            if (scheduler.next !== undefined)
                response.nextRuns[scheduler.key] = new Date(scheduler.next);

        for (const row of await this.pipelines.list()) {
            response.pipelines[row.name] = PipelineDB.toPipeline(row);
            response.schedules[row.name] = PipelineDB.toSchedule(row);
        }

        return response;
    }

    /** The enabled schedules of the pipelines Python still has. */
    public async listScheduled(): Promise<Record<Pipeline.Name, Pipeline.Schedule>> {
        const schedules: Record<Pipeline.Name, Pipeline.Schedule> = {};

        for (const row of await this.pipelines.list())
            if (row.available && row.enabled)
                schedules[row.name] = PipelineDB.toSchedule(row);

        return schedules;
    }

    public async setSchedule(name: Pipeline.Name, request: Pipeline.API.SetSchedule.Request): Promise<Pipeline.Schedule> {
        const schedule = await this.pipelines.setSchedule(name, request.cron, request.enabled);

        await this.queues.add(PipelineRunner.Queue.Reconcile.Definition, {});

        return schedule;
    }

    /** Queues a run of it now, schedule or not. */
    public async runNow(name: Pipeline.Name): Promise<void> {
        const row = await this.pipelines.get(name);

        if (!row.available)
            throw new BadRequestException(`Python no longer defines ${name}`);

        await this.queues.add(PipelineRunner.Queue.RunPipeline.Definition, {
            pipeline: name,
            cause:    'manual',
        });
    }

    public async startRun(request: Pipeline.API.Internal.StartRun.Request): Promise<Pipeline.Run> {
        const run = await this.pipelines.createRun(request.pipeline, request.cause);

        this.realtime.emitEvent({
            ...Pipeline.Event.create('pipeline:run:updated', { run }),
            channel: Pipeline.Event.RUNS_CHANNEL,
        });

        return run;
    }

    public async finishRun(id: Pipeline.Run.Id, request: Pipeline.API.Internal.FinishRun.Request): Promise<Pipeline.Run> {
        const run = await this.pipelines.finishRun(id, request);

        this.realtime.emitEvent({
            ...Pipeline.Event.create('pipeline:run:updated', { run }),
            channel: Pipeline.Event.RUNS_CHANNEL,
        });

        return run;
    }

    public listRuns(query: Pipeline.API.ListRuns.Query): Promise<Pipeline.Run[]> {
        return this.pipelines.listRuns(query);
    }

    public getRun(id: Pipeline.Run.Id): Promise<{ run: Pipeline.Run; log: string }> {
        return this.pipelines.getRun(id);
    }

    public async onModuleDestroy(): Promise<void> {
        await this.runQueue.close();
    }
}
