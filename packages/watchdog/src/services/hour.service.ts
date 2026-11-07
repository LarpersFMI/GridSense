import { Injectable } from '@nestjs/common';
import { Dataset, Forecaster, Trigger } from '@gridsense/shared/domain';
import { getServerApi } from '@gridsense/shared/server/internal-api';
import { DatasetService } from './dataset.service';

import Hour = Trigger.Check.Hour;

/** The hours a dataset update brings to check, each with every dataset's values that exist for it. */
@Injectable()
export class HourService {

    constructor(private readonly datasets: DatasetService) {}

    /**
     * The update's hours, [start, end): each with its cleared prices where they exist, and the forecast — the update's
     * run if it has one, else the latest run issued before the hours begin (what was known when they started). The run's
     * id comes back with them, or null if there was none.
     */
    public async forUpdate(update: Dataset.Update): Promise<{ runId: Forecaster.Run.Id | null; hours: Hour[] }> {
        const api = getServerApi();
        let run: Forecaster.Run | null;

        if (update.runId !== null)
            ({ run } = await Forecaster.API.Internal.getRun(api, update.runId));
        else
            ({ run } = await Forecaster.API.Internal.getLatestRun(api, { before: update.start }));

        let hours: Record<string, Hour> = {};
        let runId: Forecaster.Run.Id | null = null;

        if (run !== null) {
            hours = await this.readForecast(run, update);
            runId = run.id;
        }

        for (const price of await this.datasets.readPrices(update.start, update.end)) {
            const time = price.ts_utc.toISOString();

            if (!(time in hours))
                hours[time] = { at: price.ts_utc, values: {} };

            hours[time].values.prices = Trigger.Check.toValues(price, Dataset.PricesHourly.compute(price));
        }

        const sorted = Object.values(hours);

        sorted.sort((a, b) => a.at.getTime() - b.at.getTime());

        return { runId, hours: sorted };
    }

    /** A run's forecast hours in [start, end), by time (UTC ISO), computed against the run before. */
    public async readForecast(run: Forecaster.Run, range: { start: Date; end: Date }): Promise<Record<string, Hour>> {
        const { run: previous } = await Forecaster.API.Internal.getPreviousRun(getServerApi(), run.id);
        const previousByTime: Record<string, Dataset.Predictions.Row> = {};

        if (previous !== null)
            for (const prediction of await this.datasets.readPredictions(previous.predictionsPath, previous.issueTs))
                previousByTime[prediction.target_ts_utc.toISOString()] = prediction;

        const hours: Record<string, Hour> = {};

        for (const prediction of await this.datasets.readPredictions(run.predictionsPath, run.issueTs)) {
            const at = prediction.target_ts_utc;
            const time = at.toISOString();

            if (at < range.start || at >= range.end)
                continue;

            let previousPrediction: Dataset.Predictions.Row | null = null;

            if (time in previousByTime)
                previousPrediction = previousByTime[time];

            hours[time] = {
                at,
                values: { predictions: Trigger.Check.toValues(prediction, Dataset.Predictions.compute(prediction, previousPrediction)) },
            };
        }

        return hours;
    }
}
