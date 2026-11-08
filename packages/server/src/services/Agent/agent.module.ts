import { Module } from '@nestjs/common';
import { AgentRepository } from './agent.repository';
import { AgentService } from './agent.service';
import { AgentHttpController } from './controllers/http.controller';
import { AgentInternalHttpController } from './controllers/internal-http.controller';

/** The agent's records — threads, slots, graph — and an admin's review of a paused thread. */
@Module({
    controllers: [AgentHttpController, AgentInternalHttpController],
    providers:   [AgentService, AgentRepository],
})
export class AgentModule {}
