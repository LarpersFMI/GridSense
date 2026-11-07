import { Injectable } from '@nestjs/common';
import { Agent, Trigger, Watchdog } from '@gridsense/shared/domain';
import { QueueProducer } from '@gridsense/shared/server/queue';
import { RealtimeService } from '@gridsense/shared/server/realtime';
import { sharedRedis } from '@gridsense/shared/server/redis';

/** A trigger held: unless its window is cooling down, hand the hit to the agent and announce it. */
@Injectable()
export class HitService {

    constructor(
        private readonly queues: QueueProducer,
        private readonly realtime: RealtimeService,
    ) {}

    /** False when the same window of the same trigger hit less than cooldownMinutes ago. */
    public async raise(trigger: Trigger, hit: Trigger.Hit): Promise<boolean> {
        if (trigger.cooldownMinutes > 0) {
            const claimed = await sharedRedis().set(
                `gridsense:watchdog:cooldown:${Trigger.Hit.getCooldownKey(hit)}`,
                '1',
                'PX',
                trigger.cooldownMinutes * 60_000,
                'NX',
            );

            if (claimed === null)
                return false;
        }

        const threadId = Trigger.Hit.getThreadId(hit);

        await this.queues.add(Agent.Queue.HandleHit.Definition, hit, { jobId: threadId });

        this.realtime.emitEvent({
            ...Watchdog.Event.create('watchdog:hit:raised', { hit, threadId }),
            channel: Watchdog.Event.getTriggerChannel(trigger.id),
        });

        return true;
    }
}
