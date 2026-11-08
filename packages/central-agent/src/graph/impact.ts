import Anthropic from '@anthropic-ai/sdk';
import { zodOutputFormat } from '@anthropic-ai/sdk/helpers/zod';
import { z } from 'zod';
import type { Agent, Trigger } from '@gridsense/shared/domain';
import { System } from '@gridsense/shared/server/system';
import { AGENT_CONFIG } from '../config';
import type { Context } from './context';
import { formatWindow } from './words';

const log = System.log.withContext('Impact');

// The LLM gets this long, then the template stands.
const LLM_TIMEOUT_MS = 30_000;

// The default Claude model; AGENT_LLM_MODEL overrides it.
const DEFAULT_MODEL = 'claude-opus-5-5';

/** What the LLM writes: the prose. The impact's numbers are computed here, never by it. */
const Written = z.object({
    recommendation: z.string(),
    why:            z.string().array(),
    risks:          z.string().array(),
    unverified:     z.string().array(),
});

const SYSTEM = `You write the impact analysis an operator at PPC Energie (a Romanian electricity supplier) reads before
approving a decision about "free electricity hours": slots where the day-ahead price is forecast near zero, offered to
customers so they shift consumption into them. You get the decision (made by a rule on the forecast) and the facts the
agent's tools found, as JSON.

Rules:
- Use only numbers, dates and hours that are in the facts, written as given. Never estimate or invent one.
- Say things in plain words; never name the JSON fields (write "the chance of a near-zero price", not "pMean").
- decision.needsReview tells who decides. true: the operator approves or rejects — recommend what to do.
  false: the agent already acted on its own — say what it did and why, don't ask for approval.
- recommendation: one sentence — the decision (its label and window) and the one reason that matters most.
- why: 2–4 short points, each naming its figure and where it comes from (forecast, what the model read, the week before).
- risks: 1–3 short points — what would make this wrong (the price range, how the forecast has moved, missing inputs).
- unverified: what the facts don't cover and the operator may want to check; [] if nothing.
- Plain English, no greetings, no markdown.`;

/**
 * The impact numbers: how many customers the slot reaches and how much consumption moves into it (the pilot's figures,
 * stated as assumptions), and what that's worth — the evening's P50 against the slot's.
 */
export function computeImpact(context: Context, decision: Agent.Decision): Agent.Analysis.Impact {
    const touchesCustomers = ['likely', 'possible', 'confirmed', 'cancel'].includes(decision.label);
    const forecast = context.forecast;
    const evening = forecast?.eveningP50 ?? AGENT_CONFIG.eveningPriceEur;
    const slotPrice = context.cleared?.mean ?? forecast?.p50 ?? null;

    if (!touchesCustomers)
        return { customers: null, shiftedMwh: null, valueEur: null, basis: 'No customer-facing action.' };

    return {
        customers:  AGENT_CONFIG.pilotCustomers,
        shiftedMwh: AGENT_CONFIG.shiftedMwhPerSlot,
        valueEur:   slotPrice === null ? null : Math.round(AGENT_CONFIG.shiftedMwhPerSlot * (evening - slotPrice)),
        basis:      `Pilot assumptions: ${AGENT_CONFIG.pilotCustomers.toLocaleString('en-GB')} customers, ${AGENT_CONFIG.shiftedMwhPerSlot} MWh shifted per slot; `
            + `value = MWh × (evening ${forecast?.eveningP50 !== null && forecast?.eveningP50 !== undefined ? 'P50' : 'reference price'} ${evening.toFixed(0)} − slot ${context.cleared ? 'cleared price' : 'P50'} ${slotPrice?.toFixed(0) ?? '?'} EUR/MWh).`,
    };
}

/** The analysis without an LLM: the same facts, in fixed sentences. */
export function templateAnalysis(hit: Trigger.Hit, decision: Agent.Decision, context: Context, impact: Agent.Analysis.Impact): Agent.Analysis {
    const when = hit.window === null ? 'these hours' : formatWindow(hit.window.start, hit.window.end);
    const { forecast, inputs, trajectory, cleared, recent } = context;
    const why: string[] = [];
    const risks: string[] = [];
    const unverified: string[] = [];

    if (forecast !== null)
        why.push(`Forecast of ${forecast.issuedAt} (D+${forecast.horizon}): p_near_zero ${forecast.pMin.toFixed(2)}–${forecast.pMean.toFixed(2)} (lowest–mean), P50 ${forecast.p50.toFixed(0)} EUR/MWh.`);

    if (inputs !== null) {
        const reasons = [
            inputs.sunshine !== null ? `sunshine forecast ${inputs.sunshine.toFixed(0)} W/m²` : null,
            inputs.weekend ? 'weekend' : null,
            inputs.holiday ? 'public holiday' : null,
            inputs.negHours7d !== null ? `${inputs.negHours7d.toFixed(0)} negative-price hours the week before` : null,
        ].filter((reason) => reason !== null);

        if (reasons.length > 0)
            why.push(`What the model read: ${reasons.join(', ')}.`);
    }

    if (recent !== null)
        why.push(`The week before: ${recent.cheapMiddays} of ${recent.days} middays cleared at or under 20 EUR/MWh.`);

    if (cleared !== null)
        why.push(`The auction cleared these hours at ${cleared.mean.toFixed(1)} EUR/MWh on average, ${cleared.hoursAbove20} of ${cleared.hours} above 20.`);

    if (forecast !== null)
        risks.push(`Price range P10–P90 ${forecast.p10.toFixed(0)} to ${forecast.p90.toFixed(0)} EUR/MWh.`);

    if (trajectory.length > 1)
        risks.push(`The forecast moved ${trajectory.map((point) => point.pMean.toFixed(2)).join(' → ')} over ${trajectory.length} runs.`);

    if (inputs !== null && inputs.missingWeather > 0)
        unverified.push(`${inputs.missingWeather} hour(s) had no weather forecast.`);

    if (cleared === null && ['likely', 'possible'].includes(decision.label))
        unverified.push('The auction for these hours has not cleared yet.');

    const recommendation: Record<Agent.Decision.Label, string> = {
        likely:    `Announce ${when} as free hours (Likely) — ${decision.reason}`,
        possible:  `Free hours ${when} are Possible — announce them only if you approve: ${decision.reason}`,
        confirmed: `Confirm ${when}: the auction cleared it — ${decision.reason}`,
        cancel:    `Cancel what was announced over ${when} — ${decision.reason}`,
        alert:     `Tell the team about ${when} — ${decision.reason}`,
        none:      `Nothing to do over ${when} — ${decision.reason}`,
    };

    return {
        recommendation: recommendation[decision.label],
        why,
        impact,
        risks,
        unverified,
        writtenBy: 'template',
        at:        new Date(),
    };
}

/**
 * The impact analysis of a decision: the numbers computed from the agent's tools, the prose written by Claude from
 * them (structured output, validated), the template's otherwise — without an API key, on a refusal, an error or a
 * timeout. The decision is the rule's; the analysis only explains it.
 */
export async function analyze(trigger: Trigger, hit: Trigger.Hit, decision: Agent.Decision, context: Context): Promise<Agent.Analysis> {
    const impact = computeImpact(context, decision);
    const template = templateAnalysis(hit, decision, context, impact);

    if (!process.env.ANTHROPIC_API_KEY)
        return template;

    try {
        const client = new Anthropic({ timeout: LLM_TIMEOUT_MS, maxRetries: 1 });

        const facts = rounded({
            trigger:  { name: trigger.name, description: trigger.description, playbook: trigger.playbook },
            window:   hit.window === null ? null : formatWindow(hit.window.start, hit.window.end),
            decision: { label: decision.label, rule: decision.rule, reason: decision.reason, needsReview: decision.needsReview },
            impact,
            ...context,
        });

        // On a refusal the API re-runs the request on a fallback model it picks by the refusal's category.
        const response = await client.beta.messages.parse({
            betas:         ['server-side-fallback-2026-07-01'],
            fallbacks:     'default',
            model:         process.env.AGENT_LLM_MODEL ?? DEFAULT_MODEL,
            max_tokens:    4000,
            system:        SYSTEM,
            output_config: { effort: 'low', format: zodOutputFormat(Written) },
            messages:      [{ role: 'user', content: JSON.stringify(facts, null, 1) }],
        });

        if (response.stop_reason === 'refusal' || response.parsed_output === null) {
            log.warning('No analysis from the LLM, template kept', { stopReason: response.stop_reason });

            return template;
        }

        return { ...response.parsed_output, impact, writtenBy: 'llm', at: new Date() };
    }
    catch (error) {
        log.warning('LLM unavailable, template kept', { error });

        return template;
    }
}

/** The facts as a person would read them: probabilities to 2 decimals, prices and the rest to 1. */
function rounded(value: unknown): unknown {
    if (typeof value === 'number')
        return Math.abs(value) < 1 ? Number(value.toFixed(2)) : Number(value.toFixed(1));

    if (Array.isArray(value))
        return value.map(rounded);

    if (value !== null && typeof value === 'object')
        return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, rounded(item)]));

    return value;
}
