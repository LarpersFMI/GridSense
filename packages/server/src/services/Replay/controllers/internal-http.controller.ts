import { Controller, Get } from '@nestjs/common';
import { Replay } from '@gridsense/shared/domain';
import { ReplayRepository } from '../replay.repository';

import Internal = Replay.API.Internal;

/** For the PipelineRunner: the start it hands the replay pipelines. */
@Controller('internal/replay')
export class ReplayInternalHttpController {

    constructor(private readonly replay: ReplayRepository) {}

    @Get()
    public async get(): Promise<Internal.Get.Response> {
        return { replay: await this.replay.get() };
    }
}
