import { Module } from '@nestjs/common';
import { ForecasterHttpController } from './controllers/http.controller';
import { ForecasterInternalHttpController } from './controllers/internal-http.controller';
import { ForecasterService } from './forecaster.service';
import { RunRepository } from './run.repository';

/** The Forecaster's runs. */
@Module({
    controllers: [ForecasterHttpController, ForecasterInternalHttpController],
    providers:   [ForecasterService, RunRepository],
    exports:     [ForecasterService],
})
export class ForecasterModule {}
