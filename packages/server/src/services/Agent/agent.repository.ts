import { Injectable, NotFoundException } from '@nestjs/common';
import { sql } from 'kysely';
import { z } from 'zod';
import { Agent, Foundations, Trigger } from '@gridsense/shared/domain';
import { Repository, Transactional } from '../../db/repository';
import { json, type Table } from '../../db/table';

/** The `gridsense.agent_thread`, `agent_slot` and `agent_graph` tables: jsonb as the domain shapes, parsed on the way out. */
export namespace AgentDB {

    export const ThreadRow = z.object({
        id:         Foundations.Thread.Id,
        trigger_id: Trigger.Id,
        playbook:   Trigger.Playbook.Schema,
        status:     Agent.Thread.Status,
        hit:        z.unknown(),
        decision:   z.unknown(),
        analysis:   z.unknown(),
        actions:    z.unknown(),
        steps:      z.unknown(),
        review:     z.unknown(),
        messages:   z.unknown(),
        created_at: z.date(),
        updated_at: z.date(),
    });
    export type ThreadRow = z.infer<typeof ThreadRow>;

    export const SlotRow = z.object({
        key:        z.string(),
        starts_at:  z.date(),
        ends_at:    z.date(),
        label:      Agent.Slot.Schema.shape.label,
        status:     Agent.Slot.Status,
        thread_ids: z.unknown(),
        reason:     z.string(),
        updated_at: z.date(),
    });
    export type SlotRow = z.infer<typeof SlotRow>;

    export const GraphRow = z.object({
        id:         z.number(),
        mermaid:    z.string(),
        nodes:      z.unknown(),
        updated_at: z.date(),
    });

    export const toThread = (row: ThreadRow): Agent.Thread => Agent.Thread.Schema.parse({
        id:        row.id,
        triggerId: row.trigger_id,
        playbook:  row.playbook,
        status:    row.status,
        hit:       row.hit,
        decision:  row.decision,
        analysis:  row.analysis,
        actions:   row.actions,
        steps:     row.steps,
        review:    row.review,
        messages:  row.messages,
        createdAt: row.created_at,
        updatedAt: row.updated_at,
    });

    export const toSlot = (row: SlotRow): Agent.Slot => Agent.Slot.Schema.parse({
        key:       row.key,
        start:     row.starts_at,
        end:       row.ends_at,
        label:     row.label,
        status:    row.status,
        threadIds: row.thread_ids,
        reason:    row.reason,
        updatedAt: row.updated_at,
    });

    export interface Tables {
        'gridsense.agent_thread': Table<typeof ThreadRow, 'analysis' | 'messages' | 'created_at' | 'updated_at'>;
        'gridsense.agent_slot':   Table<typeof SlotRow, 'updated_at'>;
        'gridsense.agent_graph':  Table<typeof GraphRow, 'id' | 'updated_at'>;
    }
}

@Injectable()
export class AgentRepository extends Repository<AgentDB.Tables>() {

    /** Creates the thread, or replaces it whole; its created_at stays the first save's. */
    @Transactional()
    public async saveThread(thread: Agent.Thread): Promise<Agent.Thread> {
        const values = {
            trigger_id: thread.triggerId,
            playbook:   thread.playbook,
            status:     thread.status,
            hit:        json(thread.hit),
            decision:   json(thread.decision),
            analysis:   json(thread.analysis),
            actions:    json(thread.actions),
            steps:      json(thread.steps),
            review:     json(thread.review),
        };

        const row = await this.trx
            .insertInto('gridsense.agent_thread')
            .values({ id: thread.id, ...values })
            .onConflict((conflict) => conflict.column('id').doUpdateSet({ ...values, updated_at: new Date() }))
            .returningAll()
            .executeTakeFirstOrThrow();

        return AgentDB.toThread(row);
    }

    /** Appends one turn to the thread's conversation; the rest of the thread is left as it is. */
    @Transactional()
    public async addMessage(id: Foundations.Thread.Id, message: Agent.Message): Promise<Agent.Thread> {
        const row = await this.trx
            .updateTable('gridsense.agent_thread')
            .set({ messages: sql`messages || jsonb_build_array(${JSON.stringify(message)}::jsonb)`, updated_at: new Date() })
            .where('id', '=', id)
            .returningAll()
            .executeTakeFirst();

        if (!row)
            throw new NotFoundException(`No thread ${id}`);

        return AgentDB.toThread(row);
    }

    @Transactional()
    public async listThreads(query: Agent.API.ListThreads.Query): Promise<Agent.Thread[]> {
        let select = this.trx
            .selectFrom('gridsense.agent_thread')
            .selectAll()
            .orderBy('updated_at', 'desc')
            .limit(query.limit);

        if (query.status)
            select = select.where('status', '=', query.status);

        return (await select.execute()).map(AgentDB.toThread);
    }

    @Transactional()
    public async getThread(id: Foundations.Thread.Id): Promise<Agent.Thread> {
        const row = await this.trx
            .selectFrom('gridsense.agent_thread')
            .selectAll()
            .where('id', '=', id)
            .executeTakeFirst();

        if (!row)
            throw new NotFoundException(`No thread ${id}`);

        return AgentDB.toThread(row);
    }

    @Transactional()
    public async saveSlot(slot: Agent.Slot): Promise<Agent.Slot> {
        const values = {
            starts_at:  slot.start,
            ends_at:    slot.end,
            label:      slot.label,
            status:     slot.status,
            thread_ids: json(slot.threadIds),
            reason:     slot.reason,
        };

        const row = await this.trx
            .insertInto('gridsense.agent_slot')
            .values({ key: slot.key, ...values })
            .onConflict((conflict) => conflict.column('key').doUpdateSet({ ...values, updated_at: new Date() }))
            .returningAll()
            .executeTakeFirstOrThrow();

        return AgentDB.toSlot(row);
    }

    /** Slots starting from `from` (all without it), or overlapping [start, end). */
    @Transactional()
    public async listSlots(range: { from?: Date; start?: Date; end?: Date }): Promise<Agent.Slot[]> {
        let select = this.trx
            .selectFrom('gridsense.agent_slot')
            .selectAll()
            .orderBy('starts_at');

        if (range.from)
            select = select.where('ends_at', '>', range.from);

        if (range.start && range.end)
            select = select.where('starts_at', '<', range.end).where('ends_at', '>', range.start);

        return (await select.execute()).map(AgentDB.toSlot);
    }

    @Transactional()
    public async saveGraph(graph: Agent.Graph): Promise<void> {
        await this.trx
            .insertInto('gridsense.agent_graph')
            .values({ mermaid: graph.mermaid, nodes: json(graph.nodes) })
            .onConflict((conflict) => conflict.column('id').doUpdateSet({
                mermaid:    graph.mermaid,
                nodes:      json(graph.nodes),
                updated_at: sql<Date>`now()`,
            }))
            .execute();
    }

    @Transactional()
    public async getGraph(): Promise<Agent.Graph | null> {
        const row = await this.trx
            .selectFrom('gridsense.agent_graph')
            .selectAll()
            .executeTakeFirst();

        if (!row)
            return null;

        return Agent.Graph.Schema.parse({ mermaid: row.mermaid, nodes: row.nodes });
    }
}
