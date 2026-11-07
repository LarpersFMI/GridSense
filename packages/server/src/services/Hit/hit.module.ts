import { Module } from '@nestjs/common';
import { HitHttpController } from './controllers/http.controller';
import { HitService } from './hit.service';

/** The triggers' hits, as the agent's queue holds them. */
@Module({
    controllers: [HitHttpController],
    providers:   [HitService],
})
export class HitModule {}
