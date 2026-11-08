import { z } from "zod"

/** The agent's graph as LangGraph draws it: mermaid, and its nodes — so the UI can show which a thread went through. */
export namespace Graph {

    export const Schema = z.object({
        mermaid: z.string(),
        nodes:   z.string().array(),
    })
}
export type Graph = z.infer<typeof Graph.Schema>
