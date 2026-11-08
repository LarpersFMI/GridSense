import { Injectable } from '@nestjs/common';
import { sql } from 'kysely';
import { z } from 'zod';
import { Dataset, Pipeline, Replay } from '@gridsense/shared/domain';
import { Repository, Transactional } from '../../db/repository';
import type { Table } from '../../db/table';

/** The `gridsense.replay` row, and what a reset clears in the other tables. */
export namespace ReplayDB {

    export const Row = z.object({
        id:         z.literal(true),
        start:      z.date(),
        updated_at: z.date(),
    });
    export type Row = z.infer<typeof Row>;

    /** A `date` column comes back as local midnight in this process: its calendar day, as written. */
    export const toReplay = (row: Row): Replay => Replay.Schema.parse({
        start: `${row.start.getFullYear()}-${String(row.start.getMonth() + 1).padStart(2, '0')}-${String(row.start.getDate()).padStart(2, '0')}`,
    });

    export interface Tables {
        'gridsense.replay': Table<typeof Row, 'id' | 'updated_at'>;
    }
}

@Injectable()
export class ReplayRepository extends Repository<ReplayDB.Tables>() {

    @Transactional()
    public async get(): Promise<Replay> {
        const row = await this.trx
            .selectFrom('gridsense.replay')
            .selectAll()
            .executeTakeFirstOrThrow();

        return ReplayDB.toReplay(row);
    }

    @Transactional()
    public async setStart(start: Replay.LocalDate): Promise<Replay> {
        const row = await this.trx
            .updateTable('gridsense.replay')
            .set({ start: sql<Date>`${start}::date`, updated_at: new Date() })
            .returningAll()
            .executeTakeFirstOrThrow();

        return ReplayDB.toReplay(row);
    }

    /** Each dataset's triggers read their file from this watermark on: null reads it all. */
    @Transactional()
    public async setWatermarks(watermarks: Record<Dataset.Triggerable, Date | null>): Promise<void> {
        for (const [dataset, watermark] of Object.entries(watermarks))
            await sql`
                update gridsense.trigger set watermark = ${watermark}
                where checked_on ->> 'type' = 'dataset' and checked_on ->> 'dataset' = ${dataset}
            `.execute(this.trx);
    }

    /**
     * What the agent kept: its threads and slots, and LangGraph's checkpoints (schema `langgraph`, made when the agent
     * first starts — absent before).
     */
    @Transactional()
    public async clearAgent(): Promise<void> {
        await sql`delete from gridsense.agent_thread`.execute(this.trx);
        await sql`delete from gridsense.agent_slot`.execute(this.trx);

        for (const table of ['checkpoint_writes', 'checkpoint_blobs', 'checkpoints']) {
            const { rows } = await sql<{ present: boolean }>`select to_regclass(${`langgraph.${table}`}) is not null as present`.execute(this.trx);

            if (rows[0].present)
                await sql`delete from ${sql.table(`langgraph.${table}`)}`.execute(this.trx);
        }
    }

    /**
     * The replay pipelines' runs, and the forecast runs reported (gridsense.run): a run reported again with the same
     * issue_ts is taken as a duplicate and checked by no one, so a replay started over must find none.
     */
    @Transactional()
    public async deleteRuns(pipelines: Pipeline.Name[]): Promise<void> {
        await sql`delete from gridsense.pipeline_run where pipeline = any(${pipelines})`.execute(this.trx);
        await sql`delete from gridsense.run`.execute(this.trx);
    }
}
