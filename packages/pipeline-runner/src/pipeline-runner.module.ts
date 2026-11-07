import { BullModule } from '@nestjs/bullmq';
import { Controller, Get, Module } from '@nestjs/common';
import { PipelineRunner } from '@gridsense/shared/domain';
import { QueueModule } from '@gridsense/shared/server/queue';
import { RealtimeModule } from '@gridsense/shared/server/realtime';
import { QUEUE_PREFIX, redisConnection } from '@gridsense/shared/server/redis';
import { ReconcileProcessor } from './processors/reconcile.processor';
import { RunPipelineProcessor } from './processors/run-pipeline.processor';
import { PythonService } from './services/python.service';
import { Startup } from './startup';

@Controller('health')
export class HealthController {

    @Get()
    public health() {
        return { ok: true, worker: 'pipeline-runner' };
    }
}

/**
 * The PipelineRunner: syncs the pipelines Python defines to the server, keeps a BullMQ job scheduler per enabled
 * schedule, and runs each pipeline as a Python subprocess. No database — everything goes through /internal.
 */
@Module({
    imports: [
        BullModule.forRootAsync({ useFactory: () => ({ connection: redisConnection(), prefix: QUEUE_PREFIX }) }),
        BullModule.registerQueue(
            { name: PipelineRunner.Queue.RunPipeline.Definition.name },
            { name: PipelineRunner.Queue.Reconcile.Definition.name },
        ),
        QueueModule,
        RealtimeModule,
    ],
    controllers: [HealthController],
    providers: [
        PythonService,
        RunPipelineProcessor,
        ReconcileProcessor,
        Startup,
    ],
})
export class PipelineRunnerModule {}
