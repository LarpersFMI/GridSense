import { Controller, Get, Param } from '@nestjs/common';
import { Dataset } from '@gridsense/shared/domain';
import { ZodPipe } from '../../../http/zod.pipe';
import { DatasetService } from '../dataset.service';

import API = Dataset.API;

/** For the condition editor: what columns a dataset has, and their types. */
@Controller('api/datasets')
export class DatasetHttpController {

    constructor(private readonly service: DatasetService) {}

    @Get(':name/schema')
    public async describe(@Param(new ZodPipe(API.Describe.Params)) params: API.Describe.Params): Promise<API.Describe.Response> {
        return { description: await this.service.describe(params.name) };
    }
}
