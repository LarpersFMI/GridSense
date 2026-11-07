// load-env first: reflect-metadata and the env every other module reads.
import './load-env';

import { NestFactory } from '@nestjs/core';
import { waitForServer } from '@gridsense/shared/server/internal-api';
import { System } from '@gridsense/shared/server/system';
import { PipelineRunnerModule } from './pipeline-runner.module';

System.log.setAppName('PipelineRunner');

const log = System.log.withContext('PipelineRunner');

async function bootstrap(): Promise<void> {
    // Started alongside the server, it may come up first — definitions, schedules and runs go through its /internal API.
    await waitForServer();

    const app = await NestFactory.create(PipelineRunnerModule, { logger: ['error', 'warn'] });

    app.enableShutdownHooks();

    const port = Number(process.env.PIPELINE_RUNNER_PORT ?? 4200);

    await app.listen(port);

    log.info('Listening', { port });
}

bootstrap().catch((error: unknown) => {
    log.error('Boot failed', { error });
    process.exit(1);
});
