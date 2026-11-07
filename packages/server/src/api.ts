// Must stay first: reflect-metadata and env before anything else loads.
import './load-env';

import { NestFactory } from '@nestjs/core';
import { WsAdapter } from '@nestjs/platform-ws';
import { System } from '@gridsense/shared/server/system';
import { db } from './db/pool';
import { migrate } from './db/migrator';
import { MIGRATIONS_FOLDER } from './migrations-folder';
import { ServerModule } from './server.module';

System.log.setAppName('Server');

const log = System.log.withContext('Server');

async function bootstrap(): Promise<void> {
    // The server owns the database: workers start after it and never migrate.
    await migrate(db(), MIGRATIONS_FOLDER);

    const app = await NestFactory.create(ServerModule, { logger: ['error', 'warn'] });

    app.useWebSocketAdapter(new WsAdapter(app));
    app.enableCors();
    app.enableShutdownHooks();

    const port = Number(process.env.PORT ?? 4000);

    await app.listen(port);

    log.info('Listening', { port });
}

bootstrap().catch((error: unknown) => {
    log.error('Boot failed', { error });
    process.exit(1);
});
