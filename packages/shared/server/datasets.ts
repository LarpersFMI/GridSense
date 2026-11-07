import { resolve } from "node:path"
import { Dataset } from "../domain"
import { requireEnv } from "./env"

/** DATASET_DIR may be relative: to the repository root, where .env is. */
const REPOSITORY_ROOT = resolve(__dirname, "../../..")

const FILES: Record<Dataset.Name, string> = {
    predictions: Dataset.Predictions.FILE,
    prices:      Dataset.PricesHourly.FILE,
}

/** Where a dataset's file is: DATASET_DIR and its FILE. Every run appends its predictions to the same file. */
export const getDatasetPath = (name: Dataset.Name) => resolve(REPOSITORY_ROOT, requireEnv("DATASET_DIR"), FILES[name])

/** A column name as a SQL identifier: a trigger's incremental column comes from the admin. */
export const quoteSqlIdentifier = (name: string) => `"${name.replaceAll('"', '""')}"`

/** A path as a SQL string literal: DuckDB's read_parquet takes no bound parameter. */
export const quoteSqlPath = (path: string) => `'${path.replaceAll("'", "''")}'`

/** A DuckDB row as plain JS: BIGINT columns come back as bigint, which zod and JSON don't take. */
export function toPlainRow(row: Record<string, unknown>): Record<string, unknown> {
    const plain: Record<string, unknown> = {}

    for (const [column, value] of Object.entries(row)) {
        if (typeof value === "bigint")
            plain[column] = Number(value)
        else
            plain[column] = value
    }

    return plain
}
