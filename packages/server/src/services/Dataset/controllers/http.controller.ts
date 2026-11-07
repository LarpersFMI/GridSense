import { Controller, Get, Param, Query } from '@nestjs/common';
import { Dataset } from '@gridsense/shared/domain';
import { ZodPipe } from '../../../http/zod.pipe';
import { DatasetService } from '../dataset.service';

import API = Dataset.API;

/** For the browser: a dataset's columns (the condition editor) and its latest rows (the dataset viewer). */
@Controller('api/datasets')
export class DatasetHttpController {

    constructor(private readonly service: DatasetService) {}

    @Get(':name/schema')
    public async describe(@Param(new ZodPipe(API.Describe.Params)) params: API.Describe.Params): Promise<API.Describe.Response> {
        return { description: await this.service.describe(params.name) };
    }

    @Get(':name/preview')
    public async getPreview(
        @Param(new ZodPipe(API.GetPreview.Params)) params: API.GetPreview.Params,
        @Query(new ZodPipe(API.GetPreview.Query)) query: API.GetPreview.Query,
    ): Promise<API.GetPreview.Response> {
        return { preview: await this.service.getPreview(params.name, query) };
    }
}
