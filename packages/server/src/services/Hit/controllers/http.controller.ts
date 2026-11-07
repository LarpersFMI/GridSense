import { Controller, Get, Query } from '@nestjs/common';
import { Trigger } from '@gridsense/shared/domain';
import { ZodPipe } from '../../../http/zod.pipe';
import { HitService } from '../hit.service';

import API = Trigger.API;

/** For the activity view: the hits waiting for the agent, or handled by it. */
@Controller('api/hits')
export class HitHttpController {

    constructor(private readonly service: HitService) {}

    @Get()
    public async list(@Query(new ZodPipe(API.ListHits.Query)) query: API.ListHits.Query): Promise<API.ListHits.Response> {
        return { hits: await this.service.list(query) };
    }
}
