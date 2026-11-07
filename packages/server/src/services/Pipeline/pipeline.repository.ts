import { Injectable, NotFoundException } from '@nestjs/common';
import { z } from 'zod';
import { Pipeline } from '@gridsense/shared/domain';
import { Repository, Transactional } from '../../db/repository';
import { json, type Table } from '../../db/table';

/** The `gridsense.pipeline` and `gridsense.pipeline_run` tables. */
export namespace PipelineDB {

    export const Row = z.object({
        name:         Pipeline.Name,
        description:  z.string(),
        outputs:      Pipeline.Schema.shape.outputs,
        default_cron: z.string(),
        available:    z.boolean(),
        cron:         z.string(),
        enabled:      z.boolean(),
        synced_at:    z.date(),
    });
    export type Row = z.infer<typeof Row>;

    export const RunRow = z.object({
        id:            Pipeline.Run.Id,
        pipeline:      Pipeline.Name,
        cause:         Pipeline.Run.Cause,
        status:        Pipeline.Run.Status,
        started_at:    z.date(),
        finished_at:   z.date().nullable(),
        rows_appended: z.record(z.string(), z.number()).nullable(),
        error:         z.string().nullable(),
        log:           z.string(),
    });
    export type RunRow = z.infer<typeof RunRow>;

    export const toPipeline = (row: Row) => ({
        ...Pipeline.Schema.parse({
            name:        row.name,
            description: row.description,
            outputs:     row.outputs,
            defaultCron: row.default_cron,
        }),
        available: row.available,
    });

    export const toSchedule = (row: Row): Pipeline.Schedule => Pipeline.Schedule.Schema.parse({
        pipeline: row.name,
        cron:     row.cron,
        enabled:  row.enabled,
    });

    export const toRun = (row: RunRow): Pipeline.Run => Pipeline.Run.Schema.parse({
        id:           row.id,
        pipeline:     row.pipeline,
        cause:        row.cause,
        status:       row.status,
        startedAt:    row.started_at,
        finishedAt:   row.finished_at,
        rowsAppended: row.rows_appended,
        error:        row.error,
    });

    export interface Tables {
        'gridsense.pipeline':     Table<typeof Row, 'available' | 'enabled' | 'synced_at'>;
        'gridsense.pipeline_run': Table<typeof RunRow, 'started_at' | 'finished_at' | 'rows_appended' | 'error' | 'log'>;
    }
}

@Injectable()
export class PipelineRepository extends Repository<PipelineDB.Tables>() {

    /** Saves what Python defines: new pipelines with their default cron, disabled; the rest marked unavailable. */
    @Transactional()
    public async sync(pipelines: Pipeline[]): Promise<void> {
        await this.trx
            .updateTable('gridsense.pipeline')
            .set({ available: false })
            .execute();

        for (const pipeline of pipelines)
            await this.trx
                .insertInto('gridsense.pipeline')
                .values({
                    name:         pipeline.name,
                    description:  pipeline.description,
                    outputs:      json(pipeline.outputs),
                    default_cron: pipeline.defaultCron,
                    cron:         pipeline.defaultCron,
                })
                .onConflict((conflict) => conflict.column('name').doUpdateSet({
                    description:  pipeline.description,
                    outputs:      json(pipeline.outputs),
                    default_cron: pipeline.defaultCron,
                    available:    true,
                    synced_at:    new Date(),
                }))
                .execute();
    }

    /** Every pipeline, available or not, by name. */
    @Transactional()
    public async list(): Promise<PipelineDB.Row[]> {
        return this.trx
            .selectFrom('gridsense.pipeline')
            .selectAll()
            .orderBy('name')
            .execute();
    }

    @Transactional()
    public async setSchedule(name: Pipeline.Name, cron: string, enabled: boolean): Promise<Pipeline.Schedule> {
        const row = await this.trx
            .updateTable('gridsense.pipeline')
            .set({ cron, enabled })
            .where('name', '=', name)
            .returningAll()
            .executeTakeFirst();

        if (!row)
            throw new NotFoundException(`No pipeline ${name}`);

        return PipelineDB.toSchedule(row);
    }

    @Transactional()
    public async get(name: Pipeline.Name): Promise<PipelineDB.Row> {
        const row = await this.trx
            .selectFrom('gridsense.pipeline')
            .selectAll()
            .where('name', '=', name)
            .executeTakeFirst();

        if (!row)
            throw new NotFoundException(`No pipeline ${name}`);

        return row;
    }

    @Transactional()
    public async createRun(pipeline: Pipeline.Name, cause: Pipeline.Run.Cause): Promise<Pipeline.Run> {
        const row = await this.trx
            .insertInto('gridsense.pipeline_run')
            .values({
                id:     Pipeline.Run.createId(),
                pipeline,
                cause,
                status: 'running',
            })
            .returningAll()
            .executeTakeFirstOrThrow();

        return PipelineDB.toRun(row);
    }

    @Transactional()
    public async finishRun(id: Pipeline.Run.Id, finish: Pipeline.API.Internal.FinishRun.Request): Promise<Pipeline.Run> {
        const row = await this.trx
            .updateTable('gridsense.pipeline_run')
            .set({
                status:        finish.status,
                finished_at:   new Date(),
                rows_appended: json(finish.rowsAppended),
                error:         finish.error,
                log:           finish.log,
            })
            .where('id', '=', id)
            .returningAll()
            .executeTakeFirst();

        if (!row)
            throw new NotFoundException(`No pipeline run ${id}`);

        return PipelineDB.toRun(row);
    }

    /** Newest first. */
    @Transactional()
    public async listRuns(query: Pipeline.API.ListRuns.Query): Promise<Pipeline.Run[]> {
        let select = this.trx
            .selectFrom('gridsense.pipeline_run')
            .selectAll()
            .orderBy('started_at', 'desc')
            .limit(query.limit);

        if (query.pipeline !== undefined)
            select = select.where('pipeline', '=', query.pipeline);

        const runs: Pipeline.Run[] = [];

        for (const row of await select.execute())
            runs.push(PipelineDB.toRun(row));

        return runs;
    }

    /** Each pipeline's latest run, by pipeline. */
    @Transactional()
    public async listLastRuns(): Promise<Record<Pipeline.Name, Pipeline.Run>> {
        const rows = await this.trx
            .selectFrom('gridsense.pipeline_run')
            .selectAll()
            .distinctOn('pipeline')
            .orderBy('pipeline')
            .orderBy('started_at', 'desc')
            .execute();

        const lastRuns: Record<Pipeline.Name, Pipeline.Run> = {};

        for (const row of rows)
            lastRuns[row.pipeline] = PipelineDB.toRun(row);

        return lastRuns;
    }

    @Transactional()
    public async getRun(id: Pipeline.Run.Id): Promise<{ run: Pipeline.Run; log: string }> {
        const row = await this.trx
            .selectFrom('gridsense.pipeline_run')
            .selectAll()
            .where('id', '=', id)
            .executeTakeFirst();

        if (!row)
            throw new NotFoundException(`No pipeline run ${id}`);

        return {
            run: PipelineDB.toRun(row),
            log: row.log,
        };
    }
}
