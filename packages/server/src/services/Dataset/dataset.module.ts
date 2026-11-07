import { Module } from '@nestjs/common';
import { DatasetHttpController } from './controllers/http.controller';
import { DatasetInternalHttpController } from './controllers/internal-http.controller';
import { DatasetService } from './dataset.service';

/** The Python side's datasets: described from their files, their updates handed to the Watchdog. */
@Module({
    controllers: [DatasetHttpController, DatasetInternalHttpController],
    providers:   [DatasetService],
    exports:     [DatasetService],
})
export class DatasetModule {}
