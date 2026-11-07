import { BullModule } from '@nestjs/bullmq';
import { Controller, Get, Module } from '@nestjs/common';
import { Watchdog } from '@gridsense/shared/domain';
import { QueueModule } from '@gridsense/shared/server/queue';
import { RealtimeModule } from '@gridsense/shared/server/realtime';
import { QUEUE_PREFIX, redisConnection } from '@gridsense/shared/server/redis';
import { DatasetUpdatedProcessor } from './processors/dataset-updated.processor';
import { ReconcileProcessor } from './processors/reconcile.processor';
import { ScheduleProcessor } from './processors/schedule.processor';
import { Schedules } from './schedules';
import { DatasetService } from './services/dataset.service';
import { HitService } from './services/hit.service';
import { HourService } from './services/hour.service';

@Controller('health')
export class HealthController {

    @Get()
    public health() {
        return { ok: true, worker: 'watchdog' };
    }
}

/**
 * The Watchdog: consumes dataset updates and schedules, checks the triggers on them, hands each hit to the agent.
 * No database — triggers and runs come from the server's /internal API, rows from parquet.
 */
@Module({
    imports: [
        BullModule.forRootAsync({ useFactory: () => ({ connection: redisConnection(), prefix: QUEUE_PREFIX }) }),
        BullModule.registerQueue(
            { name: Watchdog.Queue.DatasetUpdated.Definition.name },
            { name: Watchdog.Queue.Schedule.Definition.name },
            { name: Watchdog.Queue.Reconcile.Definition.name },
        ),
        QueueModule,
        RealtimeModule,
    ],
    controllers: [HealthController],
    providers: [
        DatasetService,
        HitService,
        HourService,
        DatasetUpdatedProcessor,
        ScheduleProcessor,
        ReconcileProcessor,
        Schedules,
    ],
})
export class WatchdogModule {}
