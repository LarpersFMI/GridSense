import type { ConnectionOptions } from "bullmq"
import { Redis } from "ioredis"
import { requireEnv } from "./env"

/** Key prefix for every queue, so a shared Redis can't collide with other apps. */
export const QUEUE_PREFIX = "gridsense"

/** BullMQ's connection, from REDIS_URL. */
export function redisConnection(): ConnectionOptions {
    const url = new URL(requireEnv("REDIS_URL"))

    return {
        host:                 url.hostname,
        port:                 Number(url.port || 6379),
        username:             url.username || undefined,
        password:             url.password ? decodeURIComponent(url.password) : undefined,
        db:                   url.pathname.length > 1 ? Number(url.pathname.slice(1)) : 0,
        maxRetriesPerRequest: null,                   // required by BullMQ
    }
}

let shared: Redis | undefined

/** The process's client for plain commands: publishing events, cooldown keys. */
export const sharedRedis = (): Redis => (shared ??= new Redis(requireEnv("REDIS_URL")))

/** A client of its own: a subscribed connection can't run other commands. */
export const redisSubscriber = (): Redis => new Redis(requireEnv("REDIS_URL"))
