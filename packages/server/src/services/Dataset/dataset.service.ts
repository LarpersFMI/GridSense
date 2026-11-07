import { Injectable, type OnModuleDestroy } from '@nestjs/common';
import { DuckDBInstance, type DuckDBConnection } from '@duckdb/node-api';
import { Dataset, Watchdog } from '@gridsense/shared/domain';
import { getDatasetPath, quoteSqlPath } from '@gridsense/shared/server/datasets';
import { QueueProducer } from '@gridsense/shared/server/queue';
import { ForecasterService } from '../Forecaster/forecaster.service';

/** DuckDB's type names, by how a condition compares them. */
const NUMBER_TYPES = /^(TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT|UTINYINT|USMALLINT|UINTEGER|UBIGINT|FLOAT|DOUBLE|DECIMAL)/;
const TIMESTAMP_TYPES = /^(TIMESTAMP|DATE|TIME)/;

const COMPUTED: Record<Dataset.Name, readonly string[]> = {
    predictions: Dataset.Predictions.COMPUTED_COLUMNS,
    prices:      Dataset.PricesHourly.COMPUTED_COLUMNS,
};

/** Describes a dataset from its file as it is now, plus the columns the Watchdog computes on it; reports its updates. */
@Injectable()
export class DatasetService implements OnModuleDestroy {

    private connection: Promise<DuckDBConnection> | undefined;

    constructor(
        private readonly forecaster: ForecasterService,
        private readonly queues: QueueProducer,
    ) {}

    /** Hours of a dataset changed outside a run (the auction cleared a day): the Watchdog checks the triggers on it. */
    public async reportUpdate(name: Dataset.Name, request: Dataset.API.Internal.ReportUpdate.Request): Promise<Dataset.Update> {
        const update: Dataset.Update = {
            dataset: name,
            start:   request.start,
            end:     request.end,
            runId:   null,
        };

        await this.queues.add(Watchdog.Queue.DatasetUpdated.Definition, update, {
            jobId: Dataset.Update.getKey(update),
        });

        return update;
    }

    /** The predictions are described from the latest run's file; the prices from DATASET_DIR. */
    public async describe(name: Dataset.Name): Promise<Dataset.Description> {
        let path = getDatasetPath(name);

        if (name === 'predictions') {
            const [latest] = await this.forecaster.listRuns(1);

            if (latest)
                path = latest.predictionsPath;
        }

        const connection = await this.connect();
        const reader = await connection.runAndReadAll(`describe select * from read_parquet(${quoteSqlPath(path)})`);

        const columns: Dataset.Description.Column[] = [];

        for (const row of reader.getRowObjectsJS()) {
            const type = String(row.column_type);
            let columnType: Dataset.Description.ColumnType = 'other';

            if (NUMBER_TYPES.test(type))
                columnType = 'number';
            else if (type === 'VARCHAR' || type.startsWith('ENUM'))
                columnType = 'text';
            else if (TIMESTAMP_TYPES.test(type))
                columnType = 'timestamp';
            else if (type === 'BOOLEAN')
                columnType = 'boolean';

            columns.push({
                name:     String(row.column_name),
                type:     columnType,
                computed: false,
            });
        }

        for (const column of COMPUTED[name])
            columns.push({
                name:     column,
                type:     'number',
                computed: true,
            });

        return {
            name,
            columns,
        };
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
