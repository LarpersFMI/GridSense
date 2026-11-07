import { Processor } from '@nestjs/bullmq';
import type { Job } from 'bullmq';
import { Trigger, Watchdog } from '@gridsense/shared/domain';
import { getServerApi } from '@gridsense/shared/server/internal-api';
import { JobProcessor } from '@gridsense/shared/server/queue';
import { RealtimeService } from '@gridsense/shared/server/realtime';
import { System } from '@gridsense/shared/server/system';
import { HitService } from '../services/hit.service';

/** A trigger's schedule fired: it holds by definition (no hours to test), so its one hit goes to the agent. */
@Processor(Watchdog.Queue.Schedule.Definition.name, { concurrency: 1 })
export class ScheduleProcessor extends JobProcessor<typeof Watchdog.Queue.Schedule.Definition> {

    protected readonly definition = Watchdog.Queue.Schedule.Definition;

    private readonly log = System.log.withContext('Schedule');

    constructor(
        private readonly hits: HitService,
        private readonly realtime: RealtimeService,
    ) {
        super();
    }

    protected async handle(job: Watchdog.Queue.Schedule.Job, raw: Job): Promise<Watchdog.Queue.CheckResult> {
        const { trigger } = await Trigger.API.Internal.get(getServerApi(), job.triggerId);
        const firedAt = new Date(raw.timestamp);

        const check: Trigger.Check = {
            cause: {
                type: 'schedule',
                firedAt,
            },
            runId: null,
            hours: [],
        };

        let raised = 0;
        let cooledDown = 0;

        for (const hit of Trigger.evaluate(trigger, check)) {
            if (await this.hits.raise(trigger, hit))
                raised += 1;
            else
                cooledDown += 1;
        }

        this.realtime.emitEvent({
            ...Watchdog.Event.create('watchdog:check:completed', {
                source:          { type: 'schedule', triggerId: trigger.id, firedAt },
                triggersChecked: 1,
                hits:            raised,
                cooledDown,
                checkedAt:       new Date(),
            }),
            channel: Watchdog.Event.ACTIVITY_CHANNEL,
        });

        this.log.info('Fired', {
            trigger: trigger.name,
            hits:    raised,
        });

        return { hits: raised };
    }
}
