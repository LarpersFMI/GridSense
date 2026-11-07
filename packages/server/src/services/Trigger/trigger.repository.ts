import { ConflictException, Injectable, NotFoundException } from '@nestjs/common';
import { sql } from 'kysely';
import { z } from 'zod';
import { Dataset, Trigger } from '@gridsense/shared/domain';
import { Repository, Transactional } from '../../db/repository';
import { json, type Table } from '../../db/table';

/** The `gridsense.trigger` table: a trigger's shapes stored as jsonb, as zod validated them, and the Watchdog's watermark. */
export namespace TriggerDB {

    export const Row = z.object({
        id:               Trigger.Id,
        name:             z.string(),
        description:      z.string(),
        enabled:          z.boolean(),
        checked_on:       Trigger.On.Schema,
        match_mode:       Trigger.Condition.Match,
        conditions:       Trigger.Condition.Schema.array(),
        hit_grouping:     Trigger.Grouping.Schema,
        cooldown_minutes: z.number().int(),
        watermark:        z.date().nullable(),   // the Watchdog's: how far it has read the dataset's incremental column
        created_at:       z.date(),
        updated_at:       z.date(),
    });
    export type Row = z.infer<typeof Row>;

    export const toDomain = (row: Row): Trigger => Trigger.Schema.parse({
        id:              row.id,
        name:            row.name,
        description:     row.description,
        enabled:         row.enabled,
        on:              row.checked_on,
        match:           row.match_mode,
        conditions:      row.conditions,
        grouping:        row.hit_grouping,
        cooldownMinutes: row.cooldown_minutes,
    });

    /** The columns a trigger sets, on insert and update alike — all but its id. */
    export const fromDomain = (trigger: Trigger) => ({
        name:             trigger.name,
        description:      trigger.description,
        enabled:          trigger.enabled,
        checked_on:       json(trigger.on),
        match_mode:       trigger.match,
        conditions:       json(trigger.conditions),
        hit_grouping:     json(trigger.grouping),
        cooldown_minutes: trigger.cooldownMinutes,
    });

    export interface Tables {
        'gridsense.trigger': Table<typeof Row, 'watermark' | 'created_at' | 'updated_at'>;
    }
}

@Injectable()
export class TriggerRepository extends Repository<TriggerDB.Tables>() {

    @Transactional()
    public async list(): Promise<Record<Trigger.Id, Trigger>> {
        const rows = await this.trx
            .selectFrom('gridsense.trigger')
            .selectAll()
            .orderBy('created_at')
            .execute();

        const triggers: Record<Trigger.Id, Trigger> = {};

        for (const row of rows)
            triggers[row.id] = TriggerDB.toDomain(row);

        return triggers;
    }

    /** Enabled triggers checked when this dataset updates, and their watermarks. */
    @Transactional()
    public async listForDataset(dataset: Dataset.Name): Promise<{ triggers: Record<Trigger.Id, Trigger>; watermarks: Record<Trigger.Id, Date | null> }> {
        const rows = await this.trx
            .selectFrom('gridsense.trigger')
            .selectAll()
            .where('enabled', '=', true)
            .where(sql<string>`checked_on ->> 'type'`, '=', 'dataset')
            .where(sql<string>`checked_on ->> 'dataset'`, '=', dataset)
            .execute();

        const triggers: Record<Trigger.Id, Trigger> = {};
        const watermarks: Record<Trigger.Id, Date | null> = {};

        for (const row of rows) {
            triggers[row.id] = TriggerDB.toDomain(row);
            watermarks[row.id] = row.watermark;
        }

        return { triggers, watermarks };
    }

    /** Enabled triggers on a schedule. */
    @Transactional()
    public async listScheduled(): Promise<Record<Trigger.Id, Trigger>> {
        const rows = await this.trx
            .selectFrom('gridsense.trigger')
            .selectAll()
            .where('enabled', '=', true)
            .where(sql<string>`checked_on ->> 'type'`, '=', 'schedule')
            .execute();

        const triggers: Record<Trigger.Id, Trigger> = {};

        for (const row of rows)
            triggers[row.id] = TriggerDB.toDomain(row);

        return triggers;
    }

    @Transactional()
    public async get(id: Trigger.Id): Promise<Trigger> {
        const row = await this.trx
            .selectFrom('gridsense.trigger')
            .selectAll()
            .where('id', '=', id)
            .executeTakeFirst();

        if (!row)
            throw new NotFoundException(`No trigger ${id}`);

        return TriggerDB.toDomain(row);
    }

    /** Inserts it under its own id, reading from `watermark` on; one that exists is a conflict. */
    @Transactional()
    public async create(trigger: Trigger, watermark: Date | null): Promise<Trigger> {
        const row = await this.trx
            .insertInto('gridsense.trigger')
            .values({
                id: trigger.id,
                ...TriggerDB.fromDomain(trigger),
                watermark,
            })
            .onConflict((conflict) => conflict.column('id').doNothing())
            .returningAll()
            .executeTakeFirst();

        if (!row)
            throw new ConflictException(`Trigger ${trigger.id} exists`);

        return TriggerDB.toDomain(row);
    }

    /** Replaces it; its watermark too, unless `watermark` is undefined. */
    @Transactional()
    public async update(trigger: Trigger, watermark: Date | null | undefined): Promise<Trigger> {
        const row = await this.trx
            .updateTable('gridsense.trigger')
            .set({
                ...TriggerDB.fromDomain(trigger),
                ...(watermark === undefined ? {} : { watermark }),
                updated_at: new Date(),
            })
            .where('id', '=', trigger.id)
            .returningAll()
            .executeTakeFirst();

        if (!row)
            throw new NotFoundException(`No trigger ${trigger.id}`);

        return TriggerDB.toDomain(row);
    }

    /** The Watchdog read the trigger's rows up to here. */
    @Transactional()
    public async setWatermark(id: Trigger.Id, watermark: Date): Promise<Date> {
        const row = await this.trx
            .updateTable('gridsense.trigger')
            .set({ watermark })
            .where('id', '=', id)
            .returning('watermark')
            .executeTakeFirst();

        if (!row)
            throw new NotFoundException(`No trigger ${id}`);

        return watermark;
    }

    @Transactional()
    public async delete(id: Trigger.Id): Promise<Trigger> {
        const row = await this.trx
            .deleteFrom('gridsense.trigger')
            .where('id', '=', id)
            .returningAll()
            .executeTakeFirst();

        if (!row)
            throw new NotFoundException(`No trigger ${id}`);

        return TriggerDB.toDomain(row);
    }
}
