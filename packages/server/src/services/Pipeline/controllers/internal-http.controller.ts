import { Body, Controller, Get, Param, Post, Put } from '@nestjs/common';
import { Pipeline } from '@gridsense/shared/domain';
import { ZodPipe } from '../../../http/zod.pipe';
import { PipelineService } from '../pipeline.service';

import Internal = Pipeline.API.Internal;

/** For the PipelineRunner: what Python defines, the schedules it keeps, the runs it starts and ends. */
@Controller('internal/pipelines')
export class PipelineInternalHttpController {

    constructor(private readonly service: PipelineService) {}

    @Put()
    public async syncDefinitions(@Body(new ZodPipe(Internal.SyncDefinitions.Request)) request: Internal.SyncDefinitions.Request): Promise<Internal.SyncDefinitions.Response> {
        return { pipelines: await this.service.sync(request.pipelines) };
    }

    @Get('scheduled')
    public async listScheduled(): Promise<Internal.ListScheduled.Response> {
        return { schedules: await this.service.listScheduled() };
    }

    @Post('runs')
    public async startRun(@Body(new ZodPipe(Internal.StartRun.Request)) request: Internal.StartRun.Request): Promise<Internal.StartRun.Response> {
        return { run: await this.service.startRun(request) };
    }

    @Put('runs/:id')
    public async finishRun(
        @Param('id', new ZodPipe(Pipeline.Run.Id)) id: Pipeline.Run.Id,
        @Body(new ZodPipe(Internal.FinishRun.Request)) request: Internal.FinishRun.Request,
    ): Promise<Internal.FinishRun.Response> {
        return { run: await this.service.finishRun(id, request) };
    }
}
