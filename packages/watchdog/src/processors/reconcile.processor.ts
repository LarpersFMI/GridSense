import { InjectQueue, Processor } from '@nestjs/bullmq';
import type { Queue } from 'bullmq';
import { Time, Trigger, Watchdog } from '@gridsense/shared/domain';
import { getServerApi } from '@gridsense/shared/server/internal-api';
import { JobProcessor } from '@gridsense/shared/server/queue';
import { System } from '@gridsense/shared/server/system';

/**
 * One BullMQ job scheduler per enabled scheduled trigger, its id the trigger's: upserted with the trigger's
 * cron (Romanian time), removed when the trigger is gone, disabled or no longer on a schedule.
 */
@Processor(Watchdog.Queue.Reconcile.Definition.name, { concurrency: 1 })
export class ReconcileProcessor extends JobProcessor<typeof Watchdog.Queue.Reconcile.Definition> {

    protected readonly definition = Watchdog.Queue.Reconcile.Definition;

    private readonly log = System.log.withContext('Reconcile');

    constructor(@InjectQueue(Watchdog.Queue.Schedule.Definition.name) private readonly schedules: Queue) {
        super();
    }

    protected async handle(): Promise<Watchdog.Queue.Reconcile.Result> {
        const { triggers } = await Trigger.API.Internal.listScheduled(getServerApi());
        const wanted = new Set<string>();

        for (const trigger of Object.values(triggers)) {
            if (trigger.on.type !== 'schedule')
                continue;

            wanted.add(trigger.id);

            await this.schedules.upsertJobScheduler(
                trigger.id,
                {
                    pattern: trigger.on.cron,
                    tz:      Time.Local.TIME_ZONE,
                },
                {
                    name: Watchdog.Queue.Schedule.Definition.name,
                    data: Watchdog.Queue.Schedule.Job.parse({ triggerId: trigger.id }),
                    opts: Watchdog.Queue.Schedule.Definition.options,
                },
            );
        }

        let removed = 0;

        for (const scheduler of await this.schedules.getJobSchedulers()) {
            if (wanted.has(scheduler.key))
                continue;

            await this.schedules.removeJobScheduler(scheduler.key);
            removed += 1;
        }

        this.log.info('Schedules in line', {
            schedules: wanted.size,
            removed,
        });

        return { schedules: wanted.size };
    }
}
