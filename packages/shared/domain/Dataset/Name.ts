import { z } from "zod"

/** The datasets our TypeScript packages read, by name. */
export const Name = z.enum(["predictions", "prices"])
export type  Name = z.infer<typeof Name>
