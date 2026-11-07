import { Controller, Param, Post } from '@nestjs/common';
import { Dataset } from '@gridsense/shared/domain';
import { ZodPipe } from '../../../http/zod.pipe';
import { DatasetService } from '../dataset.service';

import Internal = Dataset.API.Internal;

/** For the Python pipeline: rows were appended to a dataset's file outside a run. */
@Controller('internal/datasets')
export class DatasetInternalHttpController {

    constructor(private readonly service: DatasetService) {}

    @Post(':name/updates')
    public async reportUpdate(@Param(new ZodPipe(Internal.ReportUpdate.Params)) params: Internal.ReportUpdate.Params): Promise<Internal.ReportUpdate.Response> {
        return { update: await this.service.reportUpdate(params.name) };
    }
}
