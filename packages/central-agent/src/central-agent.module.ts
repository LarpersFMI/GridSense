import { BullModule } from '@nestjs/bullmq';
import { Controller, Get, Module } from '@nestjs/common';
import { Agent } from '@gridsense/shared/domain';
import { QueueModule } from '@gridsense/shared/server/queue';
import { QUEUE_PREFIX, redisConnection } from '@gridsense/shared/server/redis';
import { AgentGraphService } from './graph/agent-graph.service';
import { AskProcessor } from './processors/ask.processor';
import { HandleHitProcessor } from './processors/handle-hit.processor';
import { ResumeProcessor } from './processors/resume.processor';

@Controller('health')
export class HealthController {

    @Get()
    public health() {
        return { ok: true, worker: 'central-agent' };
    }
}

/**
 * The central agent: a LangGraph graph run once per hit (`agent.handle-hit`) and resumed by the operator's review
 * (`agent.resume`); the operator's questions about a thread answered from its read-only tools (`agent.ask`). Its checkpoints are in Postgres; its threads, slots and graph go to the server's /internal API.
 */
@Module({
    imports: [
        BullModule.forRootAsync({ useFactory: () => ({ connection: redisConnection(), prefix: QUEUE_PREFIX }) }),
        BullModule.registerQueue(
            { name: Agent.Queue.HandleHit.Definition.name },
            { name: Agent.Queue.Resume.Definition.name },
            { name: Agent.Queue.Ask.Definition.name },
        ),
        QueueModule,
    ],
    controllers: [HealthController],
    providers: [
        AgentGraphService,
        HandleHitProcessor,
        ResumeProcessor,
        AskProcessor,
    ],
})
export class CentralAgentModule {}
