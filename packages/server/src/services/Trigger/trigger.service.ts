import { Injectable } from '@nestjs/common';
import { Trigger, Watchdog } from '@gridsense/shared/domain';
import { QueueProducer } from '@gridsense/shared/server/queue';
import { TriggerRepository } from './trigger.repository';

/** Writes go through here, so the Watchdog's job schedulers follow every change; reads use `triggers` directly. */
@Injectable()
export class TriggerService {

    constructor(
        public readonly triggers: TriggerRepository,
        private readonly queues: QueueProducer,
    ) {}

    public async create(trigger: Trigger): Promise<Trigger> {
        const created = await this.triggers.create(trigger);

        await this.queues.add(Watchdog.Queue.Reconcile.Definition, {});

        return created;
    }

    public async update(trigger: Trigger): Promise<Trigger> {
        const updated = await this.triggers.update(trigger);

        await this.queues.add(Watchdog.Queue.Reconcile.Definition, {});

        return updated;
    }

    public async delete(id: Trigger.Id): Promise<Trigger> {
        const trigger = await this.triggers.delete(id);

        await this.queues.add(Watchdog.Queue.Reconcile.Definition, {});

        return trigger;
    }
}
