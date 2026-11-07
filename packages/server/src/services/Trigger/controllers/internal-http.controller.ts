import { Controller, Get, Param, Query } from '@nestjs/common';
import { Trigger } from '@gridsense/shared/domain';
import { ZodPipe } from '../../../http/zod.pipe';
import { TriggerService } from '../trigger.service';

import Internal = Trigger.API.Internal;

/** For the Watchdog: the triggers it checks. */
@Controller('internal/triggers')
export class TriggerInternalHttpController {

    constructor(private readonly service: TriggerService) {}

    @Get()
    public async listForDataset(@Query(new ZodPipe(Internal.ListForDataset.Query)) query: Internal.ListForDataset.Query): Promise<Internal.ListForDataset.Response> {
        return { triggers: await this.service.triggers.listForDataset(query.dataset) };
    }

    @Get('scheduled')
    public async listScheduled(): Promise<Internal.ListScheduled.Response> {
        return { triggers: await this.service.triggers.listScheduled() };
    }

    @Get(':id')
    public async get(@Param('id', new ZodPipe(Trigger.Id)) id: Trigger.Id): Promise<Internal.Get.Response> {
        return { trigger: await this.service.triggers.get(id) };
    }
}
