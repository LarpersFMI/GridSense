import { Injectable } from '@nestjs/common';
import { Dataset, Forecaster, Time, Trigger } from '@gridsense/shared/domain';
import { getServerApi } from '@gridsense/shared/server/internal-api';
import { DatasetService } from './dataset.service';

import Hour = Trigger.Check.Hour;

const HOUR_MS = 60 * 60_000;

/** A trigger's new rows, as the hours they're about. */
export interface NewRows {
    upTo:  Date                          // the new watermark
    runId: Forecaster.Run.Id | null      // the run the hours' forecast came from, if it was reported
    hours: Hour[]
}

/** The hours a trigger's new rows are about, each with every dataset's values that exist for it. */
@Injectable()
export class HourService {

    constructor(private readonly datasets: DatasetService) {}

    /**
     * The rows past the watermark on the trigger's incremental column, as hours, or null when there are none.
     * - predictions: each hour's latest forecast among the new rows, with the cleared prices of hours already delivered;
     * - prices: the cleared hours, with the forecast each day had — the latest run issued before the day began.
     */
    public async forNewRows(on: Extract<Trigger.On, { type: 'dataset' }>, after: Date | null): Promise<NewRows | null> {
        const { rows, upTo } = await this.datasets.readNewRows(on.dataset, on.incrementalColumn, after);

        if (upTo === null)
            return null;

        let hours: Record<string, Hour> = {};
        let issueTs: Date | null = null;

        if (on.dataset === 'predictions') {
            const latest: Record<string, Dataset.Predictions.Row> = {};

            for (const raw of rows) {
                const row = Dataset.Predictions.Row.Schema.parse(raw);
                const time = row.target_ts_utc.toISOString();

                if (!(time in latest) || latest[time].issue_ts < row.issue_ts)
                    latest[time] = row;

                if (issueTs === null || row.issue_ts > issueTs)
                    issueTs = row.issue_ts;
            }

            hours = await this.readForecast(Object.values(latest));

            let from = Infinity;
            let to = -Infinity;

            for (const hour of Object.values(hours)) {
                from = Math.min(from, hour.at.getTime());
                to = Math.max(to, hour.at.getTime() + HOUR_MS);
            }

            for (const price of await this.datasets.readPrices(new Date(from), new Date(to)))
                hours[price.ts_utc.toISOString()].values.prices = Trigger.Check.toValues(price, Dataset.PricesHourly.compute(price));
        }
        else {
            const days: Record<string, string[]> = {};

            for (const raw of rows) {
                const price = Dataset.PricesHourly.Row.Schema.parse(raw);
                const time = price.ts_utc.toISOString();
                const day = Time.Local.of(price.ts_utc).day;

                hours[time] = {
                    at:     price.ts_utc,
                    values: { prices: Trigger.Check.toValues(price, Dataset.PricesHourly.compute(price)) },
                };

                if (!(day in days))
                    days[day] = [];

                days[day].push(time);
            }

            for (const [day, times] of Object.entries(days)) {
                const dayIssueTs = await this.datasets.getLatestIssueTs(Time.Local.startOfDay(day));

                if (dayIssueTs === null)
                    continue;

                const forecast: Dataset.Predictions.Row[] = [];

                for (const row of await this.datasets.readPredictions(dayIssueTs))
                    if (times.includes(row.target_ts_utc.toISOString()))
                        forecast.push(row);

                for (const [time, hour] of Object.entries(await this.readForecast(forecast)))
                    hours[time].values.predictions = hour.values.predictions;

                if (issueTs === null || dayIssueTs > issueTs)
                    issueTs = dayIssueTs;
            }
        }

        let runId: Forecaster.Run.Id | null = null;

        if (issueTs !== null) {
            const { run } = await Forecaster.API.Internal.findRun(getServerApi(), { issueTs });

            if (run !== null)
                runId = run.id;
        }

        const sorted = Object.values(hours);

        sorted.sort((a, b) => a.at.getTime() - b.at.getTime());

        return { upTo, runId, hours: sorted };
    }

    /** Forecast rows, one per hour, as hours by time (UTC ISO): computed against the same hour in the run issued before each. */
    public async readForecast(rows: Dataset.Predictions.Row[]): Promise<Record<string, Hour>> {
        const previousByIssue: Record<string, Record<string, Dataset.Predictions.Row>> = {};

        for (const row of rows) {
            const issue = row.issue_ts.toISOString();

            if (issue in previousByIssue)
                continue;

            previousByIssue[issue] = {};

            const previousIssueTs = await this.datasets.getLatestIssueTs(row.issue_ts);

            if (previousIssueTs !== null)
                for (const previous of await this.datasets.readPredictions(previousIssueTs))
                    previousByIssue[issue][previous.target_ts_utc.toISOString()] = previous;
        }

        const hours: Record<string, Hour> = {};

        for (const row of rows) {
            const time = row.target_ts_utc.toISOString();
            const previousRows = previousByIssue[row.issue_ts.toISOString()];
            let previous: Dataset.Predictions.Row | null = null;

            if (time in previousRows)
                previous = previousRows[time];

            hours[time] = {
                at:     row.target_ts_utc,
                values: { predictions: Trigger.Check.toValues(row, Dataset.Predictions.compute(row, previous)) },
            };
        }

        return hours;
    }
}
