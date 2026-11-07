import { Injectable } from '@nestjs/common';
import { Dataset, Forecaster, Watchdog } from '@gridsense/shared/domain';
import { QueueProducer } from '@gridsense/shared/server/queue';
import { RealtimeService } from '@gridsense/shared/server/realtime';
import { System } from '@gridsense/shared/server/system';
import { RunRepository } from './run.repository';

/** The Forecaster's runs: the Python pipeline reports them, the dashboard and the Watchdog read them. */
@Injectable()
export class ForecasterService {

    private readonly log = System.log.withContext('Forecaster');

    constructor(
        private readonly runs: RunRepository,
        private readonly queues: QueueProducer,
        private readonly realtime: RealtimeService,
    ) {}

    /** Records the run; a new one updates the predictions for the Watchdog and goes out live. Reporting it again changes nothing. */
    public async reportRun(report: Forecaster.Run.Report): Promise<Forecaster.Run> {
        const { run, created } = await this.runs.report(report);

        if (!created)
            return run;

        const update: Dataset.Update = {
            dataset: 'predictions',
            start:   report.start,
            end:     report.end,
            runId:   run.id,
        };

        await this.queues.add(Watchdog.Queue.DatasetUpdated.Definition, update, {
            jobId: Dataset.Update.getKey(update),
        });

        this.realtime.emitEvent({
            ...Forecaster.Event.create('forecaster:run:reported', { run }),
            channel: Forecaster.Event.RUNS_CHANNEL,
        });

        this.log.info('Run reported', {
            runId:   run.id,
            issueTs: run.issueTs,
            rows:    run.rows,
        });

        return run;
    }

    /** Newest first. */
    public listRuns(limit: number): Promise<Forecaster.Run[]> {
        return this.runs.list(limit);
    }

    public getRun(id: Forecaster.Run.Id): Promise<Forecaster.Run> {
        return this.runs.get(id);
    }

    /** The run issued just before this one, or null for the first. */
    public getPreviousRun(id: Forecaster.Run.Id): Promise<Forecaster.Run | null> {
        return this.runs.getPrevious(id);
    }

    /** The latest run issued before this instant, or null. */
    public getLatestRun(before: Date): Promise<Forecaster.Run | null> {
        return this.runs.getLatestBefore(before);
    }
}
