import { Injectable, NotFoundException } from '@nestjs/common';
import { z } from 'zod';
import { Forecaster } from '@gridsense/shared/domain';
import { Repository, Transactional } from '../../db/repository';
import type { Table } from '../../db/table';

/** The `gridsense.run` table. */
export namespace RunDB {

    export const Row = z.object({
        id:               Forecaster.Run.Id,
        issue_ts:         z.date(),
        model_version:    z.string(),
        row_count:        z.number().int(),
        predictions_path: z.string(),
        reported_at:      z.date(),
    });
    export type Row = z.infer<typeof Row>;

    export const toDomain = (row: Row): Forecaster.Run => Forecaster.Run.Schema.parse({
        id:              row.id,
        issueTs:         row.issue_ts,
        modelVersion:    row.model_version,
        rows:            row.row_count,
        predictionsPath: row.predictions_path,
        reportedAt:      row.reported_at,
    });

    export interface Tables {
        'gridsense.run': Table<typeof Row, 'reported_at'>;
    }
}

@Injectable()
export class RunRepository extends Repository<RunDB.Tables>() {

    /** Inserts the run, or returns the one already reported for its issueTs (`created: false`). */
    @Transactional()
    public async report(report: Forecaster.Run.Report): Promise<{ run: Forecaster.Run; created: boolean }> {
        const inserted = await this.trx
            .insertInto('gridsense.run')
            .values({
                id:               Forecaster.Run.createId(),
                issue_ts:         report.issueTs,
                model_version:    report.modelVersion,
                row_count:        report.rows,
                predictions_path: report.predictionsPath,
            })
            .onConflict((conflict) => conflict.column('issue_ts').doNothing())
            .returningAll()
            .executeTakeFirst();

        if (inserted)
            return { run: RunDB.toDomain(inserted), created: true };

        const existing = await this.trx
            .selectFrom('gridsense.run')
            .selectAll()
            .where('issue_ts', '=', report.issueTs)
            .executeTakeFirstOrThrow();

        return { run: RunDB.toDomain(existing), created: false };
    }

    @Transactional()
    public async get(id: Forecaster.Run.Id): Promise<Forecaster.Run> {
        const row = await this.trx
            .selectFrom('gridsense.run')
            .selectAll()
            .where('id', '=', id)
            .executeTakeFirst();

        if (!row)
            throw new NotFoundException(`No run ${id}`);

        return RunDB.toDomain(row);
    }

    /** The run issued just before this one, or null for the first. */
    @Transactional()
    public async getPrevious(id: Forecaster.Run.Id): Promise<Forecaster.Run | null> {
        const run = await this.get(id);

        const row = await this.trx
            .selectFrom('gridsense.run')
            .selectAll()
            .where('issue_ts', '<', run.issueTs)
            .orderBy('issue_ts', 'desc')
            .limit(1)
            .executeTakeFirst();

        if (!row)
            return null;

        return RunDB.toDomain(row);
    }

    /** The latest run issued before this instant, or null. */
    @Transactional()
    public async getLatestBefore(before: Date): Promise<Forecaster.Run | null> {
        const row = await this.trx
            .selectFrom('gridsense.run')
            .selectAll()
            .where('issue_ts', '<', before)
            .orderBy('issue_ts', 'desc')
            .limit(1)
            .executeTakeFirst();

        if (!row)
            return null;

        return RunDB.toDomain(row);
    }

    /** Newest first. */
    @Transactional()
    public async list(limit: number): Promise<Forecaster.Run[]> {
        const rows = await this.trx
            .selectFrom('gridsense.run')
            .selectAll()
            .orderBy('issue_ts', 'desc')
            .limit(limit)
            .execute();

        const runs: Forecaster.Run[] = [];

        for (const row of rows)
            runs.push(RunDB.toDomain(row));

        return runs;
    }
}
