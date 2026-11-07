import { Body, Controller, Get, HttpCode, Param, Post, Put, Query } from '@nestjs/common';
import { Pipeline } from '@gridsense/shared/domain';
import { ZodPipe } from '../../../http/zod.pipe';
import { PipelineService } from '../pipeline.service';

import API = Pipeline.API;

/** For the browser: the pipelines, their schedules, their runs, "Run now". */
@Controller('api/pipelines')
export class PipelineHttpController {

    constructor(private readonly service: PipelineService) {}

    @Get()
    public list(): Promise<API.List.Response> {
        return this.service.list();
    }

    // Before ':name', which would take "runs" for a name.
    @Get('runs')
    public async listRuns(@Query(new ZodPipe(API.ListRuns.Query)) query: API.ListRuns.Query): Promise<API.ListRuns.Response> {
        const runs: API.ListRuns.Response['runs'] = {};

        for (const run of await this.service.listRuns(query))
            runs[run.id] = run;

        return { runs };
    }

    @Get('runs/:id')
    public getRun(@Param('id', new ZodPipe(Pipeline.Run.Id)) id: Pipeline.Run.Id): Promise<API.GetRun.Response> {
        return this.service.getRun(id);
    }

    @Put(':name/schedule')
    public async setSchedule(
        @Param('name', new ZodPipe(Pipeline.Name)) name: Pipeline.Name,
        @Body(new ZodPipe(API.SetSchedule.Request)) request: API.SetSchedule.Request,
    ): Promise<API.SetSchedule.Response> {
        return { schedule: await this.service.setSchedule(name, request) };
    }

    @Post(':name/runs')
    @HttpCode(202)
    public async runNow(@Param('name', new ZodPipe(Pipeline.Name)) name: Pipeline.Name): Promise<API.RunNow.Response> {
        await this.service.runNow(name);

        return { queued: true };
    }
}
