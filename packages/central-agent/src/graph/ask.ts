import Anthropic from '@anthropic-ai/sdk';
import { betaZodTool } from '@anthropic-ai/sdk/helpers/beta/zod';
import { z } from 'zod';
import { Agent, Time } from '@gridsense/shared/domain';
import { getServerApi } from '@gridsense/shared/server/internal-api';
import { System } from '@gridsense/shared/server/system';
import { read } from './context';
import { formatWindow } from './words';

const log = System.log.withContext('Ask');

const LLM_TIMEOUT_MS = 60_000;
const DEFAULT_MODEL = 'claude-opus-5-5';

// Tool calls the agent may make for one answer.
const MAX_ITERATIONS = 8;

const HOUR_MS = 60 * 60_000;
const DAY_MS = 24 * HOUR_MS;

const SYSTEM = `You are GridSense's agent at PPC Energie, a Romanian electricity supplier. You plan "free electricity
hours": slots where the day-ahead price is forecast near zero, offered to customers so they move consumption into them.
A rule on the ML model's forecast decides each slot; an operator approves the uncertain ones.

The operator is asking about one of your decisions. Answer from the decision's facts below and from your tools, which
read the forecasts, what the model read, the cleared prices and the slots — everything known on the replay's current day,
nothing after it. Look things up rather than guess.

Rules:
- Use only numbers, dates and hours from the facts or the tool results. Never invent or estimate one.
- If the tools don't cover the question, say so plainly.
- You can't change the decision; the operator approves or rejects it. You may say what you would weigh.
- Be brief: 2–6 sentences, or a few short bullets starting with "- ". Plain text only: no bold, no asterisks, no
  headings, no tables.
- Times are Romanian local time.`;

const round = (value: number) => (Math.abs(value) < 1 ? Number(value.toFixed(2)) : Number(value.toFixed(1)));
const num = (value: unknown) => (typeof value === 'number' && Number.isFinite(value) ? round(value) : null);
const time = (value: unknown) => (value instanceof Date ? value.getTime() : Date.parse(String(value)));
const local = (instant: number) => {
    const { day, hour } = Time.Local.of(new Date(instant));

    return `${day} ${String(hour).padStart(2, '0')}:00`;
};

/** A local day `2025-04-30` as its [start, end) in UTC. */
function dayRange(day: string): [Date, Date] {
    const start = Time.Local.startOfDay(day);
    const next = new Date(Date.parse(`${day}T12:00:00Z`) + DAY_MS).toISOString().slice(0, 10);

    return [start, Time.Local.startOfDay(next)];
}

/**
 * The agent's read-only tools for one thread, each recording that it was consulted. They read the same files the
 * Watchdog and the analysis do; none of them writes anything.
 */
function tools(thread: Agent.Thread, consulted: string[]) {
    const window = thread.hit.window;
    const used = (name: string) => {
        if (!consulted.includes(name))
            consulted.push(name);
    };

    return [
        betaZodTool({
            name:        'get_forecast_history',
            description: "Every forecast run of this decision's hours, oldest first: for each run and hour, the chance of a near-zero price (p_near_zero, ≤ 20 EUR/MWh), of a negative one (p_cheap), the price range P10/P50/P90 and data quality.",
            inputSchema: z.object({}),
            run:         async () => {
                used('forecast history');

                if (window === null)
                    return 'This decision has no hours.';

                const rows = await read('predictions', 'target_ts_utc', window.start, window.end);

                return JSON.stringify(rows.map((row) => ({
                    issued:       local(time(row.issue_ts)),
                    hour:         local(time(row.target_ts_utc)),
                    horizon_days: num(row.horizon_days),
                    p_near_zero:  num(row.p_near_zero),
                    p_cheap:      num(row.p_cheap),
                    p10:          num(row.price_p10),
                    p50:          num(row.price_p50),
                    p90:          num(row.price_p90),
                    quality:      row.data_quality,
                })));
            },
        }),

        betaZodTool({
            name:        'get_inputs',
            description: "What the model read for this decision's hours in its latest run, hour by hour: forecast sunshine (W/m²), clouds (%), wind at 100 m (m/s), temperature (°C), public holiday, weekend, negative-price hours in the week before the run, and data quality.",
            inputSchema: z.object({}),
            run:         async () => {
                used('model inputs');

                if (window === null)
                    return 'This decision has no hours.';

                const rows = await read('features', 'target_ts_utc', window.start, window.end);
                const latest = Math.max(...rows.map((row) => time(row.issue_ts)));

                return JSON.stringify(rows.filter((row) => time(row.issue_ts) === latest).map((row) => ({
                    issued:      local(latest),
                    hour:        local(time(row.target_ts_utc)),
                    sunshine:    num(row.ghi_mean),
                    clouds:      num(row.cloud_mean),
                    wind:        num(row.wind100_mean),
                    temperature: num(row.temp_mean),
                    holiday:     row.is_holiday === 1,
                    weekend:     row.is_weekend === 1,
                    negHours7d:  num(row.neg_hours_7d),
                    quality:     row.data_quality,
                })));
            },
        }),

        betaZodTool({
            name:        'get_daily_prices',
            description: 'Cleared day-ahead prices (EUR/MWh) for each local day between two days, at most 31: the day\'s minimum, the midday (11:00–15:00) minimum and mean, and the evening (18:00–22:00) mean. Only days already cleared on the replay\'s current day.',
            inputSchema: z.object({
                from: z.string().describe('First local day, YYYY-MM-DD'),
                to:   z.string().describe('Last local day, YYYY-MM-DD'),
            }),
            run: async ({ from, to }) => {
                used('cleared prices');

                const [start] = dayRange(from);
                const [, end] = dayRange(to);

                if (end.getTime() - start.getTime() > 32 * DAY_MS)
                    return 'At most 31 days at a time.';

                const days = new Map<string, { hour: number; price: number }[]>();

                for (const row of await read('prices', 'ts_utc', start, end)) {
                    const at = Time.Local.of(new Date(time(row.ts_utc)));

                    if (typeof row.price_mean === 'number')
                        days.set(at.day, [...(days.get(at.day) ?? []), { hour: at.hour, price: row.price_mean }]);
                }

                const mean = (values: number[]) => (values.length === 0 ? null : round(values.reduce((sum, value) => sum + value, 0) / values.length));

                return JSON.stringify([...days.entries()].map(([day, hours]) => {
                    const midday = hours.filter((hour) => hour.hour >= 11 && hour.hour < 15).map((hour) => hour.price);
                    const evening = hours.filter((hour) => hour.hour >= 18 && hour.hour < 22).map((hour) => hour.price);

                    return {
                        day,
                        min:         round(Math.min(...hours.map((hour) => hour.price))),
                        middayMin:   midday.length === 0 ? null : round(Math.min(...midday)),
                        middayMean:  mean(midday),
                        eveningMean: mean(evening),
                    };
                }));
            },
        }),

        betaZodTool({
            name:        'get_hourly_prices',
            description: "One local day's cleared day-ahead prices, hour by hour (EUR/MWh), if that day has cleared.",
            inputSchema: z.object({ day: z.string().describe('Local day, YYYY-MM-DD') }),
            run:         async ({ day }) => {
                used('cleared prices');

                const [start, end] = dayRange(day);
                const rows = await read('prices', 'ts_utc', start, end);

                if (rows.length === 0)
                    return `${day} hasn't cleared yet.`;

                return JSON.stringify(rows.map((row) => ({ hour: local(time(row.ts_utc)), price: num(row.price_mean) })));
            },
        }),

        betaZodTool({
            name:        'get_slots',
            description: 'Every free-hours slot the agent has announced, confirmed or cancelled so far: its hours, label (likely/possible/confirmed), status and reason.',
            inputSchema: z.object({}),
            run:         async () => {
                used('slots');

                const { slots } = await Agent.API.listSlots(getServerApi());

                return JSON.stringify(Object.values(slots).map((slot) => ({
                    hours:  formatWindow(slot.start, slot.end),
                    label:  slot.label,
                    status: slot.status,
                    reason: slot.reason,
                })));
            },
        }),
    ];
}

/** The decision's facts, for the first turn: what the operator is asking about. */
function facts(thread: Agent.Thread): string {
    return JSON.stringify({
        hours:    thread.hit.window === null ? null : formatWindow(thread.hit.window.start, thread.hit.window.end),
        status:   thread.status,
        decision: thread.decision === null ? null : {
            label:       thread.decision.label,
            reason:      thread.decision.reason,
            needsReview: thread.decision.needsReview,
        },
        analysis: thread.analysis === null ? null : {
            recommendation: thread.analysis.recommendation,
            why:            thread.analysis.why,
            risks:          thread.analysis.risks,
            impact:         thread.analysis.impact,
        },
        review:   thread.review,
    }, null, 1);
}

/**
 * The operator's question about a thread, answered by Claude with the agent's read-only tools: it decides what to look
 * up, the tools read the data, it answers from what they returned. The conversation so far is replayed; the answer
 * records the tools it consulted. Without an API key, or if it fails, a short note says so.
 */
export async function answer(thread: Agent.Thread): Promise<Agent.Message> {
    const consulted: string[] = [];
    const at = () => new Date();

    if (!process.env.ANTHROPIC_API_KEY)
        return { role: 'agent', text: "Claude isn't set up here (no ANTHROPIC_API_KEY), so I can't look this up. The analysis above has what the agent's tools found.", at: at(), tools: [], writtenBy: 'template' };

    // The conversation as turns; the decision's facts open it.
    const messages: Anthropic.Beta.BetaMessageParam[] = [];

    thread.messages.forEach((message, index) => {
        const text = index === 0 ? `The decision I'm asking about:\n${facts(thread)}\n\n${message.text}` : message.text;

        messages.push({ role: message.role === 'operator' ? 'user' : 'assistant', content: text });
    });

    try {
        const client = new Anthropic({ timeout: LLM_TIMEOUT_MS, maxRetries: 1 });

        // On a refusal the API re-runs the request on a fallback model it picks by the refusal's category.
        const final = await client.beta.messages.toolRunner({
            betas:          ['server-side-fallback-2026-07-01'],
            fallbacks:      'default',
            model:          process.env.AGENT_LLM_MODEL ?? DEFAULT_MODEL,
            max_tokens:     4000,
            max_iterations: MAX_ITERATIONS,
            system:         SYSTEM,
            output_config:  { effort: 'low' },
            tools:          tools(thread, consulted),
            messages,
        });

        let text = '';

        if (final.stop_reason !== 'refusal')
            for (const block of final.content)
                if (block.type === 'text')
                    text += block.text;

        if (text.trim() === '')
            return { role: 'agent', text: "I couldn't put an answer together for that. Try asking it another way.", at: at(), tools: consulted, writtenBy: 'template' };

        return { role: 'agent', text: text.trim(), at: at(), tools: consulted, writtenBy: 'llm' };
    }
    catch (error) {
        log.warning('No answer from the LLM', { error });

        return { role: 'agent', text: "I couldn't reach Claude just now, so I can't look this up. Try again in a moment.", at: at(), tools: consulted, writtenBy: 'template' };
    }
}
