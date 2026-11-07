import { Injectable } from '@nestjs/common';
import { Trigger, Watchdog } from '@gridsense/shared/domain';
import { QueueProducer } from '@gridsense/shared/server/queue';
import { DatasetService } from '../Dataset/dataset.service';
import { TriggerRepository } from './trigger.repository';

/**
 * Writes go through here: a trigger on a dataset starts reading at the rows there are now (its watermark), and every
 * change reconciles the Watchdog's job schedulers. Reads use `triggers` directly.
 */
@Injectable()
export class TriggerService {

    constructor(
        public readonly triggers: TriggerRepository,
        private readonly datasets: DatasetService,
        private readonly queues: QueueProducer,
    ) {}

    public async create(trigger: Trigger): Promise<Trigger> {
        let watermark: Date | null = null;

        if (trigger.on.type === 'dataset')
            watermark = await this.datasets.getLatest(trigger.on.dataset, trigger.on.incrementalColumn);

        const created = await this.triggers.create(trigger, watermark);

        await this.queues.add(Watchdog.Queue.Reconcile.Definition, {});

        return created;
    }

    /** A trigger moved to another dataset or incremental column starts over from the rows there are now. */
    public async update(trigger: Trigger): Promise<Trigger> {
        const previous = await this.triggers.get(trigger.id);
        let watermark: Date | null | undefined = undefined;

        if (trigger.on.type === 'schedule')
            watermark = null;
        else if (previous.on.type !== 'dataset' || previous.on.dataset !== trigger.on.dataset || previous.on.incrementalColumn !== trigger.on.incrementalColumn)
            watermark = await this.datasets.getLatest(trigger.on.dataset, trigger.on.incrementalColumn);

        const updated = await this.triggers.update(trigger, watermark);

        await this.queues.add(Watchdog.Queue.Reconcile.Definition, {});

        return updated;
    }

    public async delete(id: Trigger.Id): Promise<Trigger> {
        const trigger = await this.triggers.delete(id);

        await this.queues.add(Watchdog.Queue.Reconcile.Definition, {});

        return trigger;
    }
}
