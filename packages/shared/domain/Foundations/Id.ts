import { z } from "zod"

type Uuid = `${string}-${string}-${string}-${string}-${string}`

/** Ids are UUIDv7, branded per concept so a run id can't be passed where a trigger id is expected. */
export namespace Id {

    /** `Id.define("Trigger.Id")`: the concept's id schema. */
    export const define = <B extends string>(brand: B) => z.uuid().brand(brand)
}

/** RFC 9562 UUIDv7: 48-bit millisecond timestamp, then random — time-ordered, index-friendly. */
export function uuidv7(): Uuid {
    const bytes = new Uint8Array(16)
    globalThis.crypto.getRandomValues(bytes)

    const ms = Date.now()
    bytes[0] = (ms / 2 ** 40) & 0xff
    bytes[1] = (ms / 2 ** 32) & 0xff
    bytes[2] = (ms / 2 ** 24) & 0xff
    bytes[3] = (ms / 2 ** 16) & 0xff
    bytes[4] = (ms / 2 ** 8) & 0xff
    bytes[5] = ms & 0xff
    bytes[6] = (bytes[6] & 0x0f) | 0x70     // version 7
    bytes[8] = (bytes[8] & 0x3f) | 0x80     // RFC 4122 variant

    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")

    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
