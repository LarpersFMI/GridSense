import { Injectable, type OnApplicationBootstrap } from '@nestjs/common';
import { Watchdog } from '@gridsense/shared/domain';
import { QueueProducer } from '@gridsense/shared/server/queue';

/** On boot: bring the job schedulers in line with the triggers saved while the Watchdog was down. */
@Injectable()
export class Schedules implements OnApplicationBootstrap {

    constructor(private readonly queues: QueueProducer) {}

    public async onApplicationBootstrap(): Promise<void> {
        await this.queues.add(Watchdog.Queue.Reconcile.Definition, {});
    }
}
