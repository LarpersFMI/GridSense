import { Module } from '@nestjs/common';
import { PipelineHttpController } from './controllers/http.controller';
import { PipelineInternalHttpController } from './controllers/internal-http.controller';
import { PipelineRepository } from './pipeline.repository';
import { PipelineService } from './pipeline.service';

/** The pipelines Python defines, their schedules and their runs. */
@Module({
    controllers: [PipelineHttpController, PipelineInternalHttpController],
    providers:   [PipelineService, PipelineRepository],
})
export class PipelineModule {}
