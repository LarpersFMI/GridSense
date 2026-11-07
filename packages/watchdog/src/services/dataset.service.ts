import { existsSync } from 'node:fs';
import { Injectable, type OnModuleDestroy } from '@nestjs/common';
import { DuckDBInstance, type DuckDBConnection } from '@duckdb/node-api';
import { Dataset } from '@gridsense/shared/domain';
import { getDatasetPath, quoteSqlIdentifier, quoteSqlPath, toPlainRow } from '@gridsense/shared/server/datasets';

/**
 * Reads the Python side's parquet files in DATASET_DIR with DuckDB, straight from disk. Every column comes along —
 * the row schemas are loose, so one the file adds reaches the triggers without a change here.
 */
@Injectable()
export class DatasetService implements OnModuleDestroy {

    private connection: Promise<DuckDBConnection> | undefined;

    /**
     * The rows whose incremental column is past `after` (every row when null), and the largest value among them —
     * the trigger's next watermark, or null when there are none.
     */
    public async readNewRows(name: Dataset.Name, column: string, after: Date | null): Promise<{ rows: Record<string, unknown>[]; upTo: Date | null }> {
        const connection = await this.connect();
        const quoted = quoteSqlIdentifier(column);
        let reader;

        if (after === null)
            reader = await connection.runAndReadAll(`select * from read_parquet(${quoteSqlPath(getDatasetPath(name))})`);
        else
            reader = await connection.runAndReadAll(`
                select * from read_parquet(${quoteSqlPath(getDatasetPath(name))})
                where ${quoted} > $after::timestamptz
            `, { after: after.toISOString() });

        const rows: Record<string, unknown>[] = [];
        let upTo: Date | null = null;

        for (const row of reader.getRowObjectsJS()) {
            const plain = toPlainRow(row);
            const value = plain[column];

            if (value instanceof Date && (upTo === null || value > upTo))
                upTo = value;

            rows.push(plain);
        }

        return { rows, upTo };
    }

    /** One run's predictions: the rows issued at issueTs. */
    public async readPredictions(issueTs: Date): Promise<Dataset.Predictions.Row[]> {
        const connection = await this.connect();

        const reader = await connection.runAndReadAll(`
            select * from read_parquet(${quoteSqlPath(getDatasetPath('predictions'))})
            where issue_ts = $issueTs::timestamptz
            order by target_ts_utc
        `, { issueTs: issueTs.toISOString() });

        const rows: Dataset.Predictions.Row[] = [];

        for (const row of reader.getRowObjectsJS())
            rows.push(Dataset.Predictions.Row.Schema.parse(toPlainRow(row)));

        return rows;
    }

    /** The issue_ts of the latest run issued before this instant, or null — also while there's no predictions file yet. */
    public async getLatestIssueTs(before: Date): Promise<Date | null> {
        if (!existsSync(getDatasetPath('predictions')))
            return null;

        const connection = await this.connect();

        const reader = await connection.runAndReadAll(`
            select max(issue_ts) as latest from read_parquet(${quoteSqlPath(getDatasetPath('predictions'))})
            where issue_ts < $before::timestamptz
        `, { before: before.toISOString() });

        const latest = reader.getRowObjectsJS()[0].latest;

        if (latest instanceof Date)
            return latest;

        return null;
    }

    /** Cleared prices for delivery hours in [from, to): none while there's no prices file yet (a forecast before any auction). */
    public async readPrices(from: Date, to: Date): Promise<Dataset.PricesHourly.Row[]> {
        if (!existsSync(getDatasetPath('prices')))
            return [];

        const connection = await this.connect();

        const reader = await connection.runAndReadAll(`
            select * from read_parquet(${quoteSqlPath(getDatasetPath('prices'))})
            where ts_utc >= $from::timestamptz and ts_utc < $to::timestamptz
            order by ts_utc
        `, {
            from: from.toISOString(),
            to:   to.toISOString(),
        });

        const rows: Dataset.PricesHourly.Row[] = [];

        for (const row of reader.getRowObjectsJS())
            rows.push(Dataset.PricesHourly.Row.Schema.parse(toPlainRow(row)));

        return rows;
    }

    public async onModuleDestroy(): Promise<void> {
        if (this.connection)
            (await this.connection).closeSync();
    }

    private connect(): Promise<DuckDBConnection> {
        this.connection ??= DuckDBInstance.create(':memory:').then((instance) => instance.connect());

        return this.connection;
    }
}
