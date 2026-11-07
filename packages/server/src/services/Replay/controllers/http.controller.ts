import { Body, Controller, Get, HttpCode, Post, Put } from '@nestjs/common';
import { Replay } from '@gridsense/shared/domain';
import { ZodPipe } from '../../../http/zod.pipe';
import { ReplayService } from '../replay.service';

import API = Replay.API;

/** For the browser: where the replay is, moving its start, resetting it, one step. */
@Controller('api/replay')
export class ReplayHttpController {

    constructor(private readonly service: ReplayService) {}

    @Get()
    public async get(): Promise<API.Get.Response> {
        return { replay: await this.service.get() };
    }

    @Put()
    public async setStart(@Body(new ZodPipe(API.SetStart.Request)) request: API.SetStart.Request): Promise<API.Get.Response> {
        return { replay: await this.service.setStart(request.start) };
    }

    @Post('reset')
    @HttpCode(200)
    public async reset(): Promise<API.Get.Response> {
        return { replay: await this.service.reset() };
    }

    @Post('step')
    @HttpCode(202)
    public async step(): Promise<API.Step.Response> {
        await this.service.step();

        return { queued: true };
    }
}
