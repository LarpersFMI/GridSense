import axios, { type AxiosInstance } from "axios"
import { requireEnv } from "./env"
import { System } from "./system"

const log = System.log.withContext("ServerConnection")

/** How long a worker waits for one server answer. */
const REQUEST_TIMEOUT_MS = 30_000

/** Between health checks while the server is still starting. */
const WAIT_INTERVAL_MS = 1_000

let instance: AxiosInstance | undefined

/** The server's /internal API, for the workers. Workers have no database: every read or write goes through here. */
export const getServerApi = (): AxiosInstance =>
    (instance ??= axios.create({
        baseURL: requireEnv("GRIDSENSE_SERVER_URL"),
        timeout: REQUEST_TIMEOUT_MS,
    }))

/** Blocks until the server answers its health check: started together, a worker may come up first. */
export async function waitForServer(): Promise<void> {
    for (let attempt = 1; ; attempt++) {
        try {
            await getServerApi().get("/api/health", { timeout: 2_000 })

            return
        }
        catch {
            if (attempt % 10 === 0)
                log.info(`Waiting for ${getServerApi().defaults.baseURL}…`)

            await new Promise((resolve) => setTimeout(resolve, WAIT_INTERVAL_MS))
        }
    }
}
