import { existsSync } from 'node:fs';
import { BadRequestException, Injectable, NotFoundException, type OnModuleDestroy } from '@nestjs/common';
import { DuckDBInstance, type DuckDBConnection } from '@duckdb/node-api';
import { Dataset, Watchdog } from '@gridsense/shared/domain';
import { getDatasetPath, quoteSqlIdentifier, quoteSqlPath, toPlainRow } from '@gridsense/shared/server/datasets';
import { QueueProducer } from '@gridsense/shared/server/queue';

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

    constructor(private readonly queues: QueueProducer) {}

    /** Rows were appended to a dataset's file outside a run (a day's cleared prices): the Watchdog checks the triggers on it. */
    public async reportUpdate(name: Dataset.Name): Promise<Dataset.Update> {
        const update: Dataset.Update = { dataset: name };

        await this.queues.add(Watchdog.Queue.DatasetUpdated.Definition, update);

        return update;
    }

    /**
     * The largest value of a timestamp column in a dataset's file now — a new trigger's watermark, so it reads only
     * rows appended after it was saved. Null when there's no file yet. 400 when the column isn't a timestamp in it.
     */
    public async getLatest(name: Dataset.Name, column: string): Promise<Date | null> {
        const path = getDatasetPath(name);

        if (!existsSync(path))
            return null;

        const connection = await this.connect();
        let latest: unknown;

        try {
            const reader = await connection.runAndReadAll(`select max(${quoteSqlIdentifier(column)}) as latest from read_parquet(${quoteSqlPath(path)})`);

            latest = reader.getRowObjectsJS()[0].latest;
        }
        catch {
            throw new BadRequestException(`${column} isn't a column of ${name}`);
        }

        if (latest === null)
            return null;

        if (!(latest instanceof Date))
            throw new BadRequestException(`${column} isn't a timestamp: an incremental column must be one`);

        return latest;
    }

    /**
     * The latest rows of its file: newest first by `orderBy` (a timestamp column; default the file's first), then by
     * the other timestamp columns, oldest first — a run's hours in order. Timestamps come back as ISO strings.
     */
    public async getPreview(name: Dataset.Name, query: Dataset.API.GetPreview.Query): Promise<Dataset.Preview> {
        const description = await this.describe(name);
        const columns = description.columns.filter((column) => !column.computed);
        const timestamps = columns.filter((column) => column.type === 'timestamp').map((column) => column.name);
        const orderBy = query.orderBy ?? timestamps[0] ?? columns[0].name;

        if (!columns.some((column) => column.name === orderBy))
            throw new BadRequestException(`${orderBy} isn't a column of ${name}`);

        const order = [`${quoteSqlIdentifier(orderBy)} desc`];

        for (const column of timestamps)
            if (column !== orderBy)
                order.push(`${quoteSqlIdentifier(column)} asc`);

        const path = quoteSqlPath(getDatasetPath(name));
        const connection = await this.connect();

        const reader = await connection.runAndReadAll(`
            select * from read_parquet(${path})
            order by ${order.join(', ')}
            limit ${query.limit}
        `);

        const rows: Dataset.Preview.Row[] = [];

        for (const row of reader.getRowObjectsJS()) {
            const cells: Dataset.Preview.Row = {};

            for (const [column, value] of Object.entries(toPlainRow(row))) {
                if (value instanceof Date)
                    cells[column] = value.toISOString();
                else if (typeof value === 'number' || typeof value === 'string' || typeof value === 'boolean')
                    cells[column] = value;
                else if (value === null || value === undefined)
                    cells[column] = null;
                else
                    cells[column] = String(value);
            }

            rows.push(cells);
        }

        const counted = await connection.runAndReadAll(`select count(*) as total from read_parquet(${path})`);
        const total = Number(counted.getRowObjectsJS()[0].total);

        return {
            columns,
            rows,
            orderBy,
            total,
        };
    }

    /** Described from its file in DATASET_DIR, as it is now; 404 while there's no file yet. */
    public async describe(name: Dataset.Name): Promise<Dataset.Description> {
        const path = getDatasetPath(name);

        if (!existsSync(path))
            throw new NotFoundException(
                `There's no ${name} file yet (${path}). Run the pipeline, or the replay: uv run python -m gridsense.replay --from 2026-05-13 --to 2026-05-15 --step`,
            );
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
