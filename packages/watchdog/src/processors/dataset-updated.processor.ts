import { Processor } from '@nestjs/bullmq';
import { Dataset, Trigger, Watchdog } from '@gridsense/shared/domain';
import { getServerApi } from '@gridsense/shared/server/internal-api';
import { JobProcessor } from '@gridsense/shared/server/queue';
import { RealtimeService } from '@gridsense/shared/server/realtime';
import { System } from '@gridsense/shared/server/system';
import { HitService } from '../services/hit.service';
import { HourService } from '../services/hour.service';

/**
 * A dataset's file changed: each enabled trigger on it reads its rows past its watermark, is evaluated on the hours
 * they're about, raises its hits, then moves its watermark up. A trigger with no new rows isn't checked.
 */
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
        const api = getServerApi();
        const { triggers, watermarks } = await Trigger.API.Internal.listForDataset(api, { dataset: update.dataset });

        let checked = 0;
        let raised = 0;
        let cooledDown = 0;

        for (const trigger of Object.values(triggers)) {
            if (trigger.on.type !== 'dataset')
                continue;

            const after = watermarks[trigger.id];
            let read;

            // One trigger's incremental column gone from the file mustn't stop the others.
            try {
                read = await this.hours.forNewRows(trigger.on, after);
            }
            catch (error) {
                this.log.warning('Could not read new rows', {
                    trigger: trigger.name,
                    column:  trigger.on.incrementalColumn,
                    error:   String(error),
                });

                continue;
            }

            if (read === null)
                continue;

            const check: Trigger.Check = {
                cause: {
                    type:              'dataset',
                    dataset:           trigger.on.dataset,
                    incrementalColumn: trigger.on.incrementalColumn,
                    after,
                    upTo:              read.upTo,
                },
                runId: read.runId,
                hours: read.hours,
            };

            for (const hit of Trigger.evaluate(trigger, check)) {
                if (await this.hits.raise(trigger, hit))
                    raised += 1;
                else
                    cooledDown += 1;
            }

            await Trigger.API.Internal.setWatermark(api, trigger.id, { watermark: read.upTo });

            checked += 1;
        }

        this.realtime.emitEvent({
            ...Watchdog.Event.create('watchdog:check:completed', {
                source:          { type: 'dataset', dataset: update.dataset },
                triggersChecked: checked,
                hits:            raised,
                cooledDown,
                checkedAt:       new Date(),
            }),
            channel: Watchdog.Event.ACTIVITY_CHANNEL,
        });

        this.log.info('Checked', {
            dataset:  update.dataset,
            triggers: checked,
            hits:     raised,
            cooledDown,
        });

        return { hits: raised };
    }
}
