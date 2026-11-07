import { z } from "zod"

/** The datasets our TypeScript packages read, by name. */
export const Name = z.enum(["predictions", "prices", "features"])
export type  Name = z.infer<typeof Name>

/**
 * The ones triggers are checked on: the Watchdog reads their hours (a forecast, an auction day). `features` — what the
 * model read — is for looking at, not for triggers.
 */
export const Triggerable = Name.extract(["predictions", "prices"])
export type  Triggerable = z.infer<typeof Triggerable>
