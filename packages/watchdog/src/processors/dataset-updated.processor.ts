import { Processor } from '@nestjs/bullmq';
import { Dataset, Trigger, Watchdog } from '@gridsense/shared/domain';
import { getServerApi } from '@gridsense/shared/server/internal-api';
import { JobProcessor } from '@gridsense/shared/server/queue';
import { RealtimeService } from '@gridsense/shared/server/realtime';
import { System } from '@gridsense/shared/server/system';
import { HitService } from '../services/hit.service';
import { HourService } from '../services/hour.service';

/** A dataset's hours changed: check every enabled trigger on it against those hours, and raise their hits. */
@Processor(Watchdog.Queue.DatasetUpdated.Definition.name, { concurrency: 1 })
export class DatasetUpdatedProcessor extends JobProcessor<typeof Watchdog.Queue.DatasetUpdated.Definition> {

    protected readonly definition = Watchdog.Queue.DatasetUpdated.Definition;

    private readonly log = System.log.withContext('DatasetUpdated');

    constructor(
        private readonly hours: HourService,
        private readonly hits: HitService,
        private readonly realtime: RealtimeService,
    ) {
        super();
    }

    protected async handle(update: Dataset.Update): Promise<Watchdog.Queue.CheckResult> {
        const { triggers } = await Trigger.API.Internal.listForDataset(getServerApi(), { dataset: update.dataset });
        const { runId, hours } = await this.hours.forUpdate(update);

        const check: Trigger.Check = {
            cause: {
                type: 'dataset',
                update,
            },
            runId,
            hours,
        };

        let raised = 0;
        let cooledDown = 0;

        for (const trigger of Object.values(triggers))
            for (const hit of Trigger.evaluate(trigger, check)) {
                if (await this.hits.raise(trigger, hit))
                    raised += 1;
                else
                    cooledDown += 1;
            }

        this.realtime.emitEvent({
            ...Watchdog.Event.create('watchdog:check:completed', {
                cause:           check.cause,
                triggersChecked: Object.keys(triggers).length,
                hits:            raised,
                cooledDown,
                checkedAt:       new Date(),
            }),
            channel: Watchdog.Event.ACTIVITY_CHANNEL,
        });

        this.log.info('Checked', {
            dataset:  update.dataset,
            triggers: Object.keys(triggers).length,
            hours:    hours.length,
            hits:     raised,
            cooledDown,
        });

        return { hits: raised };
    }
}
