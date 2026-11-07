import { Module } from '@nestjs/common';
import { TriggerHttpController } from './controllers/http.controller';
import { TriggerInternalHttpController } from './controllers/internal-http.controller';
import { TriggerRepository } from './trigger.repository';
import { TriggerService } from './trigger.service';

/** The admin's triggers. */
@Module({
    controllers: [TriggerHttpController, TriggerInternalHttpController],
    providers:   [TriggerService, TriggerRepository],
})
export class TriggerModule {}
