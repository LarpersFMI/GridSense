import { Body, Controller, Get, Param, Post, Query } from '@nestjs/common';
import { Forecaster } from '@gridsense/shared/domain';
import { ZodPipe } from '../../../http/zod.pipe';
import { ForecasterService } from '../forecaster.service';

import Internal = Forecaster.API.Internal;

/** For the Python pipeline (reports runs) and the Watchdog (reads them). */
@Controller('internal/runs')
export class ForecasterInternalHttpController {

    constructor(private readonly service: ForecasterService) {}

    @Post()
    public async reportRun(@Body(new ZodPipe(Internal.ReportRun.Request)) request: Internal.ReportRun.Request): Promise<Internal.ReportRun.Response> {
        return { run: await this.service.reportRun(request) };
    }

    // Before ':id', which would take "latest" for an id.
    @Get('latest')
    public async getLatestRun(@Query(new ZodPipe(Internal.GetLatestRun.Query)) query: Internal.GetLatestRun.Query): Promise<Internal.GetLatestRun.Response> {
        return { run: await this.service.getLatestRun(query.before) };
    }

    @Get(':id')
    public async getRun(@Param('id', new ZodPipe(Forecaster.Run.Id)) id: Forecaster.Run.Id): Promise<Internal.GetRun.Response> {
        return { run: await this.service.getRun(id) };
    }

    @Get(':id/previous')
    public async getPreviousRun(@Param('id', new ZodPipe(Forecaster.Run.Id)) id: Forecaster.Run.Id): Promise<Internal.GetPreviousRun.Response> {
        return { run: await this.service.getPreviousRun(id) };
    }
}
