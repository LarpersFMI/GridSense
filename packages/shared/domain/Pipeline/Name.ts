import { z } from "zod"

/** A pipeline's name, as its Python function is registered: `@pipeline("prices")`. */
export const Name = z.string().regex(/^[a-z][a-z0-9-]*$/, "Lowercase letters, digits and dashes")
export type  Name = z.infer<typeof Name>
