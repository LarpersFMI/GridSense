import { BadRequestException, Body, Controller, Delete, Get, Param, Post, Put } from '@nestjs/common';
import { Trigger } from '@gridsense/shared/domain';
import { ZodPipe } from '../../../http/zod.pipe';
import { TriggerService } from '../trigger.service';

import API = Trigger.API;

/** The admin's triggers. */
@Controller('api/triggers')
export class TriggerHttpController {

    constructor(private readonly service: TriggerService) {}

    @Get()
    public async list(): Promise<API.List.Response> {
        return { triggers: await this.service.triggers.list() };
    }

    @Get(':id')
    public async get(@Param('id', new ZodPipe(Trigger.Id)) id: Trigger.Id): Promise<API.Get.Response> {
        return { trigger: await this.service.triggers.get(id) };
    }

    @Post()
    public async create(@Body(new ZodPipe(API.Create.Request)) request: API.Create.Request): Promise<API.Create.Response> {
        return { trigger: await this.service.create(request) };
    }

    @Put(':id')
    public async update(
        @Param('id', new ZodPipe(Trigger.Id)) id: Trigger.Id,
        @Body(new ZodPipe(API.Update.Request)) request: API.Update.Request,
    ): Promise<API.Update.Response> {
        if (request.id !== id)
            throw new BadRequestException(`The trigger in the body is ${request.id}, not ${id}`);

        return { trigger: await this.service.update(request) };
    }

    @Delete(':id')
    public async delete(@Param('id', new ZodPipe(Trigger.Id)) id: Trigger.Id): Promise<API.Delete.Response> {
        return { trigger: await this.service.delete(id) };
    }
}
