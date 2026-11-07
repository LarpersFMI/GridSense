# Handling a hit

_**Planned, not built.** The contracts exist in `shared/domain/Agent` (queues and events); the `central-agent` package doesn't yet. This page is the design the code will follow._

A job on `agent.handle-hit` — a `Trigger.Hit`, its job id the hit's thread id ([raising-a-hit.md](raising-a-hit.md)). The agent decides what the hit means and acts; when it isn't sure, it pauses and asks an admin.

## The graph

One LangGraph.js graph, one **thread per hit**: `thread_id = threadId`, checkpointed in Postgres, so a paused thread survives a restart.

```mermaid
flowchart LR
    load["load<br/>trigger, run, hours<br/>(/internal)"] --> decide["decide<br/>rules on the model's numbers:<br/>Likely · Possible · nothing"]
    decide -->|nothing| dismissed(["dismissed"])
    decide -->|sure| act
    decide -->|not sure| review["review<br/>interrupt()"]
    review -->|approve| act["act<br/>notify segments · .ics · alert · report"]
    review -->|reject| dismissed
    act --> acted(["acted"])
```

The decision is **deterministic, in code**, on the model's outputs in the hit's evidence (`p_near_zero`, `interval_width`, `data_quality`, …). The LLM only writes the text — the notification, the reason, the report — from those numbers, with a template fallback when it's unavailable.

## Handling

```mermaid
sequenceDiagram
    autonumber
    participant Q as agent.handle-hit
    participant G as central-agent graph (thread = threadId)
    participant API as server /internal
    participant R as Redis pub/sub

    Q->>G: job: Trigger.Hit (id = threadId) → invoke(hit, { thread_id })
    G->>R: agent:thread:updated { status: running, step: load } on agent:thread:<threadId>
    G->>API: GET trigger, run, …
    G->>G: decide
    alt sure
        G->>G: act
        G->>R: agent:thread:updated { status: acted }
        G-->>Q: { outcome: acted }
    else not sure
        G->>G: interrupt() — checkpoint saved
        G->>R: agent:thread:updated { status: awaiting-review }
        G->>R: agent:review:requested { threadId, hit, proposal, reason } on agent:inbox
        G-->>Q: { outcome: awaiting-review } — the job ends, the thread waits
    end
```

The job doesn't wait for the admin: it ends at the pause. The thread lives in the checkpoint until a decision comes.

## Review and resume

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser (admin inbox)
    participant S as server
    participant Q as agent.resume
    participant G as central-agent graph
    participant R as Redis pub/sub

    R-->>B: agent:review:requested (inbox, live)
    B->>S: POST /api/reviews/:threadId { decision: approve | reject, note }
    S->>Q: add { threadId, decision, note }
    S->>R: agent:review:resolved { threadId, decision } on agent:inbox
    Q->>G: job → invoke(Command({ resume: { decision, note } }), { thread_id })
    G->>G: act or dismiss
    G->>R: agent:thread:updated { status: acted | dismissed }
```

## Outcomes

`Agent.Queue.Outcome`: `acted` (carried out its actions) · `awaiting-review` (paused) · `dismissed` (nothing to do, or rejected). `Agent.Event.Thread.Status` adds `running` and `failed` for the live view.

## To decide

- Where actions and the decision trace are stored (a `gridsense.thread` table, or only LangGraph's checkpoints).
- The review endpoint's home: a `Review` service on the server, or the agent's own HTTP.
- Superseding: a later hit on the same window (T2 "forecast dropped", T3 "forecast miss") should find the earlier thread's announcement and correct it — by window key.
