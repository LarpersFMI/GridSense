import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { sql, type Kysely } from 'kysely';
import { System } from '@gridsense/shared/server/system';

const log = System.log.withContext('Migrator');

/** Applies the folder's `NNN_name.sql` files not applied yet, in order, each in its own transaction. */
export async function migrate(database: Kysely<unknown>, folder: string): Promise<void> {
    await sql`create table if not exists public.gridsense_migration (
        name       text primary key,
        applied_at timestamptz not null default now()
    )`.execute(database);

    const applied = new Set<string>();
    const { rows } = await sql<{ name: string }>`select name from public.gridsense_migration`.execute(database);

    for (const row of rows)
        applied.add(row.name);

    const files = readdirSync(folder).filter((file) => file.endsWith('.sql')).sort();

    for (const file of files) {
        if (applied.has(file))
            continue;

        await database.transaction().execute(async (trx) => {
            await sql.raw(readFileSync(join(folder, file), 'utf8')).execute(trx);
            await sql`insert into public.gridsense_migration (name) values (${file})`.execute(trx);
        });

        log.info('Applied migration', { file });
    }
}
