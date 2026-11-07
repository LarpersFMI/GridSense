import { Injectable, type OnModuleDestroy } from '@nestjs/common';
import { DuckDBInstance, type DuckDBConnection } from '@duckdb/node-api';
import { Dataset } from '@gridsense/shared/domain';
import { getDatasetPath, quoteSqlPath, toPlainRow } from '@gridsense/shared/server/datasets';

/**
 * Reads the Python side's parquet files with DuckDB, straight from disk. Every column comes along — the row
 * schemas are loose, so one the file adds reaches the triggers without a change here.
 */
@Injectable()
export class DatasetService implements OnModuleDestroy {

    private connection: Promise<DuckDBConnection> | undefined;

    /** A run's predictions: the rows of predictionsPath issued at issueTs. */
    public async readPredictions(predictionsPath: string, issueTs: Date): Promise<Dataset.Predictions.Row[]> {
        const connection = await this.connect();

        const reader = await connection.runAndReadAll(`
            select * from read_parquet(${quoteSqlPath(predictionsPath)})
            where issue_ts = $issueTs::timestamptz
            order by target_ts_utc
        `, { issueTs: issueTs.toISOString() });

        const rows: Dataset.Predictions.Row[] = [];

        for (const row of reader.getRowObjectsJS())
            rows.push(Dataset.Predictions.Row.Schema.parse(toPlainRow(row)));

        return rows;
    }

    /** Cleared prices for delivery hours in [from, to). */
    public async readPrices(from: Date, to: Date): Promise<Dataset.PricesHourly.Row[]> {
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
