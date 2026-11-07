import { Module } from '@nestjs/common';
import { DatasetModule } from '../Dataset/dataset.module';
import { ReplayHttpController } from './controllers/http.controller';
import { ReplayInternalHttpController } from './controllers/internal-http.controller';
import { ReplayRepository } from './replay.repository';
import { ReplayService } from './replay.service';

/** The replay: its start, where it is, a step and a reset. */
@Module({
    imports:     [DatasetModule],
    controllers: [ReplayHttpController, ReplayInternalHttpController],
    providers:   [ReplayService, ReplayRepository],
})
export class ReplayModule {}
