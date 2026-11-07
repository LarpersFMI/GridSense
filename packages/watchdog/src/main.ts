// load-env first: reflect-metadata and the env every other module reads.
import './load-env';

import { NestFactory } from '@nestjs/core';
import { waitForServer } from '@gridsense/shared/server/internal-api';
import { System } from '@gridsense/shared/server/system';
import { WatchdogModule } from './watchdog.module';

System.log.setAppName('Watchdog');

const log = System.log.withContext('Watchdog');

async function bootstrap(): Promise<void> {
    // Started alongside the server, it may come up first — every check needs the server's /internal API.
    await waitForServer();

    const app = await NestFactory.create(WatchdogModule, { logger: ['error', 'warn'] });

    app.enableShutdownHooks();

    const port = Number(process.env.WATCHDOG_PORT ?? 4100);

    await app.listen(port);

    log.info('Listening', { port });
}

bootstrap().catch((error: unknown) => {
    log.error('Boot failed', { error });
    process.exit(1);
});
