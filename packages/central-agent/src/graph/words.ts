import Anthropic from '@anthropic-ai/sdk';
import { Time, type Agent, type Trigger } from '@gridsense/shared/domain';
import { System } from '@gridsense/shared/server/system';

const log = System.log.withContext('Words');

// The LLM gets this long, then the template stands.
const LLM_TIMEOUT_MS = 20_000;

// The default Claude model; AGENT_LLM_MODEL overrides it.
const DEFAULT_MODEL = 'claude-opus-5-5';

const SYSTEM = 'You word short operational messages for PPC Energie, a Romanian electricity supplier. Rewrite the draft for its audience in at most 3 sentences. Keep every number, date and hour exactly; add no facts, no promises, no greetings. Reply with the message only.';

const DAY = new Intl.DateTimeFormat('en-GB', { timeZone: Time.Local.TIME_ZONE, weekday: 'long', day: 'numeric', month: 'long' });
const HOUR = new Intl.DateTimeFormat('en-GB', { timeZone: Time.Local.TIME_ZONE, hour: '2-digit', minute: '2-digit' });

/** `Saturday 16 May, 09:00–15:00`, Romanian time. */
export const formatWindow = (start: Date, end: Date) => `${DAY.format(start)}, ${HOUR.format(start)}–${HOUR.format(end)}`;

/** What a message says, as facts; `template` is the message without an LLM. */
export interface Draft {
    type:     Agent.Action.Type
    audience: Agent.Action.Audience
    title:    string
    template: string
}

/**
 * Words a draft for its audience. With ANTHROPIC_API_KEY set, the LLM rewrites the template — every number kept,
 * nothing added; it gets no personal data, only the facts here. Without it, or if it fails, the template is sent.
 */
export async function word(draft: Draft, trigger: Trigger): Promise<Agent.Action> {
    const base = {
        type:     draft.type,
        audience: draft.audience,
        title:    draft.title,
        at:       new Date(),
    };

    if (!process.env.ANTHROPIC_API_KEY)
        return { ...base, text: draft.template, wordedBy: 'template' };

    try {
        const client = new Anthropic({ timeout: LLM_TIMEOUT_MS, maxRetries: 1 });

        // On a refusal the API re-runs the request on a fallback model it picks by the refusal's category.
        const reply = await client.beta.messages.create({
            betas:         ['server-side-fallback-2026-07-01'],
            fallbacks:     'default',
            model:         process.env.AGENT_LLM_MODEL ?? DEFAULT_MODEL,
            max_tokens:    2000,
            system:        SYSTEM,
            output_config: { effort: 'low' },
            messages:      [{ role: 'user', content: `Audience: ${draft.audience}\nWhy: ${trigger.description}\nDraft: ${draft.template}` }],
        });

        let text = '';

        if (reply.stop_reason !== 'refusal')
            for (const block of reply.content)
                if (block.type === 'text')
                    text += block.text;

        text = text.trim();

        if (text === '')
            return { ...base, text: draft.template, wordedBy: 'template' };

        return { ...base, text, wordedBy: 'llm' };
    }
    catch (error) {
        log.warning('LLM unavailable, template sent', { error });

        return { ...base, text: draft.template, wordedBy: 'template' };
    }
}
