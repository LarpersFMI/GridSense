import { Injectable, type OnApplicationBootstrap } from '@nestjs/common';
import { Pipeline, PipelineRunner } from '@gridsense/shared/domain';
import { getServerApi } from '@gridsense/shared/server/internal-api';
import { QueueProducer } from '@gridsense/shared/server/queue';
import { System } from '@gridsense/shared/server/system';
import { PythonService } from './services/python.service';

/**
 * On boot: tell the server which pipelines Python defines (the server then reconciles the schedulers), and reconcile
 * anyway — if Python can't be read, the schedules saved before still run.
 */
@Injectable()
export class Startup implements OnApplicationBootstrap {

    private readonly log = System.log.withContext('Startup');

    constructor(
        private readonly python: PythonService,
        private readonly queues: QueueProducer,
    ) {}

    public async onApplicationBootstrap(): Promise<void> {
        try {
            const pipelines = await this.python.listPipelines();

            await Pipeline.API.Internal.syncDefinitions(getServerApi(), { pipelines });

            this.log.info('Pipelines synced', { pipelines: pipelines.map((pipeline) => pipeline.name) });
        }
        catch (error) {
            this.log.error("Couldn't read the pipelines from Python", { error });

            await this.queues.add(PipelineRunner.Queue.Reconcile.Definition, {});
        }
    }
}
