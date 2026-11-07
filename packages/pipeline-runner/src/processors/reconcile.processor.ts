import { InjectQueue, Processor } from '@nestjs/bullmq';
import type { Queue } from 'bullmq';
import { Pipeline, PipelineRunner, Time } from '@gridsense/shared/domain';
import { getServerApi } from '@gridsense/shared/server/internal-api';
import { JobProcessor } from '@gridsense/shared/server/queue';
import { System } from '@gridsense/shared/server/system';

/**
 * One BullMQ job scheduler per enabled schedule, its id the pipeline's name: upserted with the schedule's cron
 * (Romanian time), removed when the schedule is switched off or Python no longer has the pipeline.
 */
@Processor(PipelineRunner.Queue.Reconcile.Definition.name, { concurrency: 1 })
export class ReconcileProcessor extends JobProcessor<typeof PipelineRunner.Queue.Reconcile.Definition> {

    protected readonly definition = PipelineRunner.Queue.Reconcile.Definition;

    private readonly log = System.log.withContext('Reconcile');

    constructor(@InjectQueue(PipelineRunner.Queue.RunPipeline.Definition.name) private readonly runs: Queue) {
        super();
    }

    protected async handle(): Promise<PipelineRunner.Queue.Reconcile.Result> {
        const { schedules } = await Pipeline.API.Internal.listScheduled(getServerApi());
        const wanted = new Set<string>();

        for (const schedule of Object.values(schedules)) {
            wanted.add(schedule.pipeline);

            await this.runs.upsertJobScheduler(
                schedule.pipeline,
                {
                    pattern: schedule.cron,
                    tz:      Time.Local.TIME_ZONE,
                },
                {
                    name: PipelineRunner.Queue.RunPipeline.Definition.name,
                    data: PipelineRunner.Queue.RunPipeline.Job.parse({ pipeline: schedule.pipeline, cause: 'schedule' }),
                    opts: PipelineRunner.Queue.RunPipeline.Definition.options,
                },
            );
        }

        let removed = 0;

        for (const scheduler of await this.runs.getJobSchedulers()) {
            if (wanted.has(scheduler.key))
                continue;

            await this.runs.removeJobScheduler(scheduler.key);
            removed += 1;
        }

        this.log.info('Schedules in line', {
            schedules: wanted.size,
            removed,
        });

        return { schedules: wanted.size };
    }
}
