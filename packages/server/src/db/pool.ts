import { Kysely, PostgresDialect } from 'kysely';
import { Pool, types as pgTypes } from 'pg';
import { requireEnv } from '@gridsense/shared/server/env';

const OID_INT8 = 20;

// bigint columns (counts) come back as strings by default; every value we store fits in a double.
pgTypes.setTypeParser(OID_INT8, (value) => Number(value));

let instance: Kysely<unknown> | undefined;

/** One pool for the whole process. Each repository's tables are a typed view over it. */
export const db = (): Kysely<unknown> =>
    (instance ??= new Kysely<unknown>({
        dialect: new PostgresDialect({
            pool: new Pool({
                connectionString: requireEnv('DATABASE_URL'),
                max:              10,
            }),
        }),
    }));

export async function destroyPool(): Promise<void> {
    await instance?.destroy();
    instance = undefined;
}
