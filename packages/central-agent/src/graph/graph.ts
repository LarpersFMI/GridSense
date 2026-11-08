import { Command, END, interrupt, START, StateGraph, type BaseCheckpointSaver } from '@langchain/langgraph';
import { Agent, Trigger } from '@gridsense/shared/domain';
import { getServerApi } from '@gridsense/shared/server/internal-api';
import { gatherContext } from './context';
import { decide } from './decide';
import { analyze } from './impact';
import { State, type Update } from './state';
import { formatWindow, word, type Draft } from './words';

/** What an admin answers a paused thread with: `Command({ resume })`. */
export type ReviewAnswer = Pick<Agent.Thread.Review, 'decision' | 'note'>;

/**
 * The agent's graph, one thread per hit:
 *
 *   load → decide ─┬─ analyze ─┬─ act ──────────────┐
 *                  │           └─ approval ─┬─ act ─┤→ end
 *                  ├─ act (alerts)        └─ dismiss┤
 *                  └─ dismiss ──────────────────────┘
 *
 * `decide` is the playbook's rule on the model's numbers; `analyze` runs the agent's tools over the hit's hours and
 * writes the impact analysis (the LLM explains, it never decides); `approval` pauses the thread (`interrupt`) until an
 * operator answers through `agent.resume`; `act` writes the slots and words the messages. Every node saves the
 * thread, so the UI follows it live.
 */
export function buildGraph(checkpointer: BaseCheckpointSaver) {
    return new StateGraph(State)
        .addNode('load', recorded(load))
        .addNode('decide', recorded(decideNode))
        .addNode('analyze', recorded(analyzeNode))
        .addNode('approval', recorded(approval))
        .addNode('act', recorded(act))
        .addNode('dismiss', recorded(dismiss))
        .addEdge(START, 'load')
        .addEdge('load', 'decide')
        .addConditionalEdges('decide', afterDecide, ['analyze', 'act', 'dismiss'])
        .addConditionalEdges('analyze', afterAnalyze, ['act', 'approval'])
        .addConditionalEdges('approval', afterApproval, ['act', 'dismiss'])
        .addEdge('act', END)
        .addEdge('dismiss', END)
        .compile({ checkpointer });
}

export type AgentGraph = ReturnType<typeof buildGraph>;

export { Command };

/** The trigger behind the hit, and the slots already over its window. */
async function load(state: State): Promise<Update> {
    const api = getServerApi();
    const hit = Trigger.Hit.Schema.parse(state.hit);
    const { trigger } = await Trigger.API.Internal.get(api, hit.triggerId);

    let slots: Agent.Slot[] = [];

    if (hit.window !== null)
        slots = Object.values((await Agent.API.Internal.listSlots(api, { start: hit.window.start, end: hit.window.end })).slots);

    let over = 'no window';

    if (hit.window !== null)
        over = formatWindow(hit.window.start, hit.window.end);

    return {
        trigger,
        slots,
        steps: [step('load', `Read "${trigger.name}" (playbook ${trigger.playbook}) and ${slots.length} slot(s) already over ${over}.`, {
            playbook:     trigger.playbook,
            window:       hit.window,
            matchedHours: hit.matchedHours,
            slots:        slots.map((slot) => ({ key: slot.key, label: slot.label, status: slot.status })),
        })],
    };
}

async function decideNode(state: State): Promise<Update> {
    const hit = Trigger.Hit.Schema.parse(state.hit);
    const slots = state.slots.map((slot) => Agent.Slot.Schema.parse(slot));
    const trigger = requireTrigger(state);
    const decision = decide(trigger, hit, slots);
    const superseded = await supersede(state.threadId, trigger, hit);

    let next = 'act on it';

    if (decision.label === 'none')
        next = 'nothing to do';
    else if (decision.needsReview)
        next = 'an operator decides';

    let summary = `${decision.label} — ${decision.reason} (${next})`;

    if (superseded.length > 0)
        summary += `. Closed ${superseded.length} older request(s) for the operator over these hours.`;

    return {
        decision,
        steps: [step('decide', summary, {
            rule:             decision.rule,
            confidence:       decision.confidence,
            expectedValueEur: decision.expectedValueEur,
            inputs:           decision.inputs,
            superseded,
        })],
    };
}

/**
 * Requests still waiting for the operator over the same hours: this newer hit — a fresher forecast, the auction —
 * answers them, so they're closed (dismissed, with why) and the inbox holds only what's still open. Their checkpoint
 * stays paused; the review endpoint takes only threads awaiting review.
 */
async function supersede(threadId: Agent.Thread.Id, trigger: Trigger, hit: Trigger.Hit): Promise<Agent.Thread.Id[]> {
    if (hit.window === null)
        return [];

    const api = getServerApi();
    const { threads } = await Agent.API.listThreads(api, { status: 'awaiting-review', limit: 500 });
    const closed: Agent.Thread.Id[] = [];

    for (const thread of Object.values(threads)) {
        const window = thread.hit.window;

        if (thread.id === threadId || window === null || window.start >= hit.window.end || hit.window.start >= window.end)
            continue;

        await Agent.API.Internal.saveThread(api, {
            thread: {
                ...thread,
                status:    'dismissed',
                steps:     [...thread.steps, step('dismiss', `Superseded: "${trigger.name}" answered these hours first, so the operator isn't asked any more.`, { by: threadId })],
                updatedAt: new Date(),
            },
        });
        closed.push(thread.id);
    }

    return closed;
}

function afterDecide(state: State): 'analyze' | 'act' | 'dismiss' {
    if (state.decision === null || state.decision.label === 'none')
        return 'dismiss';

    // Alerts tell a team; there's no customer impact to weigh.
    if (state.decision.label === 'alert')
        return 'act';

    return 'analyze';
}

/** The agent's tools over the hit's hours, then the impact analysis of the decision. */
async function analyzeNode(state: State): Promise<Update> {
    const hit = Trigger.Hit.Schema.parse(state.hit);
    const decision = state.decision!;
    const context = await gatherContext(hit);
    const analysis = await analyze(requireTrigger(state), hit, decision, context);

    const tools = [
        `forecast ${context.forecast === null ? 'none' : `of ${context.forecast.issuedAt}`}`,
        `${context.trajectory.length} earlier run(s)`,
        context.inputs === null ? 'no features' : 'features',
        context.cleared === null ? 'not cleared yet' : 'cleared prices',
        context.recent === null ? 'no recent prices' : `${context.recent.days} recent days`,
    ];

    return {
        analysis,
        steps: [step('analyze', `${analysis.recommendation} (written by ${analysis.writtenBy === 'llm' ? 'Claude' : 'the template'})`, {
            tools,
            impact: analysis.impact,
        })],
    };
}

function afterAnalyze(state: State): 'act' | 'approval' {
    return state.decision?.needsReview ? 'approval' : 'act';
}

/** Pauses until an admin answers. On resume the node runs again from the top, and `interrupt` returns the answer. */
async function approval(state: State): Promise<Update> {
    const answer = interrupt<{ decision: Agent.Decision | null }, ReviewAnswer>({ decision: state.decision });

    let summary = `Approved by the operator`;

    if (answer.decision === 'reject')
        summary = `Rejected by the operator`;

    if (answer.note)
        summary += `: "${answer.note}"`;

    return {
        review: { ...answer, at: new Date() },
        steps:  [step('approval', summary, { decision: answer.decision, note: answer.note })],
    };
}

function afterApproval(state: State): 'act' | 'dismiss' {
    return state.review?.decision === 'approve' ? 'act' : 'dismiss';
}

/** The playbook's actions: the slots written, and a message for each audience, worded. */
async function act(state: State): Promise<Update> {
    const api = getServerApi();
    const trigger = requireTrigger(state);
    const hit = Trigger.Hit.Schema.parse(state.hit);
    const decision = state.decision!;
    const slots = state.slots.map((slot) => Agent.Slot.Schema.parse(slot)).filter((slot) => slot.status !== 'cancelled');
    const drafts: Draft[] = [];
    const written: string[] = [];

    const saveSlot = async (slot: Agent.Slot) => {
        await Agent.API.Internal.saveSlot(api, { slot });
        written.push(`${slot.key} ${slot.status}`);
    };

    if (trigger.playbook === 'announce-slot' && hit.window !== null) {
        const when = formatWindow(hit.window.start, hit.window.end);

        await saveSlot({
            key:       hit.window.key,
            start:     hit.window.start,
            end:       hit.window.end,
            label:     decision.label === 'likely' ? 'likely' : 'possible',
            status:    'announced',
            threadIds: [state.threadId],
            reason:    decision.reason,
            updatedAt: new Date(),
        });

        drafts.push({
            type:     'announce',
            audience: 'customers',
            title:    `Free electricity hours: ${when}`,
            template: `Electricity is expected to be free ${when} (${Math.round((decision.confidence ?? 0) * 100)}% likely). Shift your washing, charging and heating into these hours; we'll confirm after tomorrow's auction.`,
        });
    }

    if (trigger.playbook === 'confirm-slot' && hit.window !== null) {
        const when = formatWindow(hit.window.start, hit.window.end);
        const announced = slots[0] ?? null;

        await saveSlot({
            key:       announced?.key ?? hit.window.key,
            start:     announced?.start ?? hit.window.start,
            end:       announced?.end ?? hit.window.end,
            label:     'confirmed',
            status:    'confirmed',
            threadIds: [...(announced?.threadIds ?? []), state.threadId],
            reason:    decision.reason,
            updatedAt: new Date(),
        });

        drafts.push({
            type:     'confirm',
            audience: 'customers',
            title:    `Confirmed: free electricity ${when}`,
            template: `Confirmed: electricity is free ${when}. The day-ahead auction cleared at ${decision.inputs.clearedPrice?.toFixed(1) ?? 'or below 0'} EUR/MWh.`,
        });
    }

    if (trigger.playbook === 'cancel-slot') {
        for (const slot of slots) {
            await saveSlot({
                ...slot,
                status:    'cancelled',
                threadIds: [...slot.threadIds, state.threadId],
                reason:    decision.reason,
                updatedAt: new Date(),
            });

            drafts.push({
                type:     'cancel',
                audience: 'customers',
                title:    `Cancelled: free hours ${formatWindow(slot.start, slot.end)}`,
                template: `The free hours announced for ${formatWindow(slot.start, slot.end)} are cancelled: the price is no longer expected to be near zero. Normal tariffs apply.`,
            });
        }
    }

    if (trigger.playbook === 'alert') {
        const audience = Object.keys(hit.evidence).some((key) => key.startsWith('predictions.data_quality')) ? 'data-owner' : 'trading-desk';
        let when = '';

        if (hit.window !== null)
            when = ` for ${formatWindow(hit.window.start, hit.window.end)}`;

        drafts.push({
            type:     'alert',
            audience,
            title:    trigger.name,
            template: `${trigger.name}${when}: ${trigger.description} ${hit.matchedHours} hour(s) matched. ${summarizeEvidence(hit.evidence)}`,
        });
    }

    const actions: Agent.Action[] = [];

    for (const draft of drafts)
        actions.push(await word(draft, trigger));

    return {
        actions,
        steps: [step('act', `${actions.length} message(s) to ${[...new Set(actions.map((action) => action.audience))].join(', ') || 'nobody'}; slots ${written.join(', ') || 'unchanged'}.`, {
            slots:    written,
            wordedBy: actions.map((action) => action.wordedBy),
        })],
    };
}

async function dismiss(state: State): Promise<Update> {
    let summary = state.decision?.reason ?? 'Nothing to do.';

    if (state.review?.decision === 'reject')
        summary = `Not acted on: the operator rejected it.`;

    return { steps: [step('dismiss', summary, {})] };
}

/** The thread as the server keeps it, from the state as it is after a node. */
export function toThread(state: State, status: Agent.Thread.Status): Agent.Thread {
    const hit = Trigger.Hit.Schema.parse(state.hit);

    return Agent.Thread.Schema.parse({
        id:        state.threadId,
        triggerId: hit.triggerId,
        playbook:  state.trigger?.playbook ?? 'alert',
        status,
        hit,
        decision:  state.decision,
        analysis:  state.analysis,
        actions:   state.actions,
        steps:     state.steps,
        review:    state.review,
        createdAt: state.createdAt,
        updatedAt: new Date(),
    });
}

/** Runs a node, then saves the thread with what it added — the UI follows each step as it happens. */
function recorded(node: (state: State) => Promise<Update>) {
    return async (state: State): Promise<Update> => {
        const update = await node(state);

        // As the reducers will merge it: actions and steps appended, the rest replaced.
        const after = {
            ...state,
            ...update,
            actions: [...state.actions, ...((update.actions ?? []) as Agent.Action[])],
            steps:   [...state.steps, ...((update.steps ?? []) as Agent.Thread.Step[])],
        } as State;

        await Agent.API.Internal.saveThread(getServerApi(), { thread: toThread(after, 'running') });

        return update;
    };
}

function requireTrigger(state: State): Trigger {
    if (state.trigger === null)
        throw new Error('The trigger was not loaded');

    return Trigger.Schema.parse(state.trigger);
}

function step(node: string, summary: string, data: Record<string, unknown>): Agent.Thread.Step {
    return { node, at: new Date(), summary, data };
}

/** `predictions.p_near_zero 0.91 (0.86–0.95)` for the columns the conditions read. */
function summarizeEvidence(evidence: Record<string, number>): string {
    const parts: string[] = [];

    for (const [key, mean] of Object.entries(evidence)) {
        if (!key.endsWith('.mean'))
            continue;

        const column = key.slice(0, -'.mean'.length);
        const low = evidence[`${column}.min`];
        const high = evidence[`${column}.max`];

        parts.push(`${column} ${mean.toFixed(2)}${low !== undefined && high !== undefined ? ` (${low.toFixed(2)}–${high.toFixed(2)})` : ''}`);
    }

    return parts.join(', ');
}
