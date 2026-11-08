import { Module } from '@nestjs/common';
import { QueueModule } from '@gridsense/shared/server/queue';
import { RealtimeModule } from '@gridsense/shared/server/realtime';
import { HealthController } from './http/health.controller';
import { AgentModule } from './services/Agent/agent.module';
import { DatasetModule } from './services/Dataset/dataset.module';
import { ForecasterModule } from './services/Forecaster/forecaster.module';
import { HitModule } from './services/Hit/hit.module';
import { PipelineModule } from './services/Pipeline/pipeline.module';
import { ReplayModule } from './services/Replay/replay.module';
import { RealtimeGatewayModule } from './services/Realtime/realtime-gateway.module';
import { TriggerModule } from './services/Trigger/trigger.module';

/** The server: runs and triggers in Postgres, /api for the browser, /internal for the workers, /socket for live events. */
@Module({
    imports: [
        QueueModule,
        RealtimeModule,
        RealtimeGatewayModule,
        ForecasterModule,
        TriggerModule,
        HitModule,
        PipelineModule,
        ReplayModule,
        AgentModule,
        DatasetModule,
    ],
    controllers: [HealthController],
})
export class ServerModule {}
