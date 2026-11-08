// load-env first: reflect-metadata and the env every other module reads.
import './load-env';

import { NestFactory } from '@nestjs/core';
import { waitForServer } from '@gridsense/shared/server/internal-api';
import { System } from '@gridsense/shared/server/system';
import { CentralAgentModule } from './central-agent.module';

System.log.setAppName('Agent');

const log = System.log.withContext('Agent');

async function bootstrap(): Promise<void> {
    // Started alongside the server: triggers, slots and threads go through its /internal API.
    await waitForServer();

    const app = await NestFactory.create(CentralAgentModule, { logger: ['error', 'warn'] });

    app.enableShutdownHooks();

    const port = Number(process.env.AGENT_PORT ?? 4300);

    await app.listen(port);

    log.info('Listening', { port });
}

bootstrap().catch((error: unknown) => {
    log.error('Boot failed', { error });
    process.exit(1);
});
