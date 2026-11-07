import type { z } from 'zod';
import { sql, type ColumnType, type Generated } from 'kysely';

/**
 * Kysely is generic over an interface of these — keys are schema-qualified table names
 * (`'gridsense.trigger'`). `Gen` lists the columns Postgres fills in, so they stay optional on insert.
 */
export type Table<T extends z.ZodTypeAny, Gen extends keyof z.output<T> = never> = {
    [K in keyof z.output<T>]: K extends Gen
        ? Generated<z.output<T>[K]>
        : ColumnType<z.output<T>[K], z.output<T>[K], z.output<T>[K]>
};

/** A jsonb value: node-postgres would turn a JS array into a Postgres array literal, so values go in as JSON text. */
export const json = <T>(value: T) => sql<T>`${JSON.stringify(value)}::jsonb`;
