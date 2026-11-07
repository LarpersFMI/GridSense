import { Controller, Get, Query } from '@nestjs/common';
import { Forecaster } from '@gridsense/shared/domain';
import { ZodPipe } from '../../../http/zod.pipe';
import { ForecasterService } from '../forecaster.service';

import API = Forecaster.API;

@Controller('api/runs')
export class ForecasterHttpController {

    constructor(private readonly service: ForecasterService) {}

    @Get()
    public async listRuns(@Query(new ZodPipe(API.ListRuns.Query)) query: API.ListRuns.Query): Promise<API.ListRuns.Response> {
        return { runs: await this.service.listRuns(query.limit) };
    }
}
