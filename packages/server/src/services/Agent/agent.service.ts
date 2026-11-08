import { BadRequestException, Injectable } from '@nestjs/common';
import { Agent, Foundations } from '@gridsense/shared/domain';
import { QueueProducer } from '@gridsense/shared/server/queue';
import { RealtimeService } from '@gridsense/shared/server/realtime';
import { AgentRepository } from './agent.repository';

/**
 * The agent's records: threads as the central agent saves them (each save goes out live), slots, its graph. An
 * admin's review is queued for the agent (`agent.resume`), which resumes the paused thread.
 */
@Injectable()
export class AgentService {

    constructor(
        private readonly agent: AgentRepository,
        private readonly queues: QueueProducer,
        private readonly realtime: RealtimeService,
    ) {}

    public async saveThread(thread: Agent.Thread): Promise<Agent.Thread> {
        const saved = await this.agent.saveThread(thread);

        this.realtime.emitEvent({
            ...Agent.Event.create('agent:thread:updated', { thread: saved }),
            channel: Agent.Event.THREADS_CHANNEL,
        });

        return saved;
    }

    public async listThreads(query: Agent.API.ListThreads.Query): Promise<Agent.API.ListThreads.Response> {
        const threads: Agent.API.ListThreads.Response['threads'] = {};

        for (const thread of await this.agent.listThreads(query))
            threads[thread.id] = thread;

        return { threads };
    }

    public getThread(id: Foundations.Thread.Id): Promise<Agent.Thread> {
        return this.agent.getThread(id);
    }

    /** Only a thread awaiting review can be answered; the agent resumes it from its checkpoint. */
    public async review(id: Foundations.Thread.Id, request: Agent.API.Review.Request): Promise<void> {
        const thread = await this.agent.getThread(id);

        if (thread.status !== 'awaiting-review')
            throw new BadRequestException(`Thread ${id} is ${thread.status}, not awaiting review`);

        await this.queues.add(Agent.Queue.Resume.Definition, {
            threadId: id,
            decision: request.decision,
            note:     request.note,
        });
    }

    /** The operator's question goes on the thread at once (live); the agent answers it from its tools (`agent.ask`). */
    public async ask(id: Foundations.Thread.Id, question: string): Promise<void> {
        await this.addMessage(id, { role: 'operator', text: question, at: new Date(), tools: [], calls: [], writtenBy: null });

        await this.queues.add(Agent.Queue.Ask.Definition, { threadId: id, question });
    }

    public async addMessage(id: Foundations.Thread.Id, message: Agent.Message): Promise<Agent.Thread> {
        const thread = await this.agent.addMessage(id, message);

        this.realtime.emitEvent({
            ...Agent.Event.create('agent:thread:updated', { thread }),
            channel: Agent.Event.THREADS_CHANNEL,
        });

        return thread;
    }

    public async saveSlot(slot: Agent.Slot): Promise<Agent.Slot> {
        const saved = await this.agent.saveSlot(slot);

        this.realtime.emitEvent({
            ...Agent.Event.create('agent:slot:updated', { slot: saved }),
            channel: Agent.Event.SLOTS_CHANNEL,
        });

        return saved;
    }

    public async listSlots(range: { from?: Date; start?: Date; end?: Date }): Promise<Record<string, Agent.Slot>> {
        const slots: Record<string, Agent.Slot> = {};

        for (const slot of await this.agent.listSlots(range))
            slots[slot.key] = slot;

        return slots;
    }

    public saveGraph(graph: Agent.Graph): Promise<void> {
        return this.agent.saveGraph(graph);
    }

    public getGraph(): Promise<Agent.Graph | null> {
        return this.agent.getGraph();
    }

    /** The slots still on — confirmed and likely, not cancelled — as an iCalendar file any calendar app imports. */
    public async getCalendar(): Promise<string> {
        const lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//GridSense//Zero-cost hours//EN', 'CALSCALE:GREGORIAN'];
        const stamp = toIcsDate(new Date());

        for (const slot of await this.agent.listSlots({})) {
            if (slot.status === 'cancelled' || slot.label === 'possible')
                continue;

            lines.push(
                'BEGIN:VEVENT',
                `UID:${slot.key}@gridsense`,
                `DTSTAMP:${stamp}`,
                `DTSTART:${toIcsDate(slot.start)}`,
                `DTEND:${toIcsDate(slot.end)}`,
                `SUMMARY:Zero-cost hours (${slot.status === 'confirmed' ? 'confirmed' : 'likely'})`,
                `DESCRIPTION:${slot.reason.replace(/[,;\\]/g, (character) => `\\${character}`).replace(/\n/g, '\\n')}`,
                'END:VEVENT',
            );
        }

        lines.push('END:VCALENDAR');

        return `${lines.join('\r\n')}\r\n`;
    }
}

/** `20260516T060000Z` */
const toIcsDate = (date: Date) => date.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
