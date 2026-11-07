import { Body, Controller, Param, Post } from '@nestjs/common';
import { Dataset } from '@gridsense/shared/domain';
import { ZodPipe } from '../../../http/zod.pipe';
import { DatasetService } from '../dataset.service';

import Internal = Dataset.API.Internal;

/** For the Python pipeline: a dataset's hours changed outside a run. */
@Controller('internal/datasets')
export class DatasetInternalHttpController {

    constructor(private readonly service: DatasetService) {}

    @Post(':name/updates')
    public async reportUpdate(
        @Param(new ZodPipe(Internal.ReportUpdate.Params)) params: Internal.ReportUpdate.Params,
        @Body(new ZodPipe(Internal.ReportUpdate.Request)) request: Internal.ReportUpdate.Request,
    ): Promise<Internal.ReportUpdate.Response> {
        return { update: await this.service.reportUpdate(params.name, request) };
    }
}
