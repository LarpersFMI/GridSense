import type { Agent, Trigger } from '@gridsense/shared/domain';
import { AGENT_CONFIG } from '../config';

/**
 * The decision, per playbook — deterministic, on the model's numbers the hit carries (its evidence: each condition's
 * column, min / mean / max over the matched hours). The LLM never decides.
 */
export function decide(trigger: Trigger, hit: Trigger.Hit, slots: Agent.Slot[]): Agent.Decision {
    const evidence = hit.evidence;
    const live = slots.filter((slot) => slot.status !== 'cancelled');

    switch (trigger.playbook) {
        case 'announce-slot':
            return decideAnnounce(hit, evidence, live);
        case 'confirm-slot':
            return decideConfirm(hit, evidence, live);
        case 'cancel-slot':
            return decideCancel(hit, evidence, live);
        case 'alert':
            return decideAlert(hit, evidence);
    }
}

function decideAnnounce(hit: Trigger.Hit, evidence: Record<string, number>, live: Agent.Slot[]): Agent.Decision {
    const minP = evidence['predictions.p_near_zero.min'];
    const meanP = evidence['predictions.p_near_zero.mean'];
    const inputs: Record<string, number> = { matchedHours: hit.matchedHours };

    if (hit.window === null || minP === undefined || meanP === undefined)
        return none('announce.needs-p', "The hit has no window, or its trigger doesn't read p_near_zero: nothing to announce.", inputs);

    inputs.minP = minP;
    inputs.meanP = meanP;

    if (live.length > 0)
        return none('announce.already', `Already announced over these hours (${live.map((slot) => slot.label).join(', ')}).`, inputs);

    // Not every matched hour had data_quality = ok: the forecast is less sure.
    const okHours = evidence['predictions.data_quality=ok'];
    const isDegraded = okHours !== undefined && okHours < hit.matchedHours;
    const slotP50 = evidence['predictions.price_p50.mean'];
    const slotPrice = slotP50 ?? 0;
    const expectedValueEur = Math.round(hit.window.hours * AGENT_CONFIG.shiftedMwhPerHour * (AGENT_CONFIG.eveningPriceEur - slotPrice) * meanP);

    if (slotP50 !== undefined)
        inputs.slotPriceP50 = slotP50;

    if (minP >= AGENT_CONFIG.likelyMinP && !isDegraded)
        return {
            label:            'likely',
            confidence:       meanP,
            expectedValueEur,
            needsReview:      false,
            rule:             'announce.likely',
            reason:           `Every hour has p_near_zero ≥ ${AGENT_CONFIG.likelyMinP} (lowest ${minP.toFixed(2)}): announced as Likely.`,
            inputs,
        };

    if (minP >= AGENT_CONFIG.possibleMinP)
        return {
            label:            'possible',
            confidence:       meanP,
            expectedValueEur,
            needsReview:      true,
            rule:             isDegraded ? 'announce.degraded' : 'announce.possible',
            reason:           isDegraded
                ? `Inputs were degraded for some hours: an operator decides (lowest p ${minP.toFixed(2)}).`
                : `Every hour has p_near_zero ≥ ${AGENT_CONFIG.possibleMinP} but not all reach ${AGENT_CONFIG.likelyMinP} (lowest ${minP.toFixed(2)}): Possible, an operator decides.`,
            inputs,
        };

    return none('announce.too-unsure', `The lowest hour has p_near_zero ${minP.toFixed(2)}, under ${AGENT_CONFIG.possibleMinP}: not worth announcing.`, inputs);
}

function decideConfirm(hit: Trigger.Hit, evidence: Record<string, number>, live: Agent.Slot[]): Agent.Decision {
    const price = evidence['prices.price_mean.mean'];
    const inputs: Record<string, number> = { matchedHours: hit.matchedHours, announcedSlots: live.length };

    if (hit.window === null)
        return none('confirm.needs-window', 'The hit has no window of hours to confirm.', inputs);

    if (price !== undefined)
        inputs.clearedPrice = price;

    return {
        label:            'confirmed',
        confidence:       1,
        expectedValueEur: Math.round(hit.window.hours * AGENT_CONFIG.shiftedMwhPerHour * (AGENT_CONFIG.eveningPriceEur - (price ?? 0))),
        needsReview:      false,
        rule:             live.length > 0 ? 'confirm.announced' : 'confirm.surprise',
        reason:           live.length > 0
            ? `The auction cleared these hours at ${formatPrice(price)}: the announced slot is confirmed.`
            : `The auction cleared these hours at ${formatPrice(price)} and nothing was announced: a surprise free slot.`,
        inputs,
    };
}

function decideCancel(hit: Trigger.Hit, evidence: Record<string, number>, live: Agent.Slot[]): Agent.Decision {
    const inputs: Record<string, number> = { matchedHours: hit.matchedHours, announcedSlots: live.length };

    for (const [key, value] of Object.entries(evidence))
        if (key.endsWith('.mean'))
            inputs[key] = value;

    if (live.length === 0)
        return none('cancel.nothing', 'Nothing was announced over these hours: nothing to cancel.', inputs);

    return {
        label:            'cancel',
        confidence:       null,
        expectedValueEur: null,
        needsReview:      true,
        rule:             'cancel.announced',
        reason:           `${live.length} announced slot(s) overlap hours that no longer hold: cancelling reaches customers, so an admin approves.`,
        inputs,
    };
}

function decideAlert(hit: Trigger.Hit, evidence: Record<string, number>): Agent.Decision {
    return {
        label:            'alert',
        confidence:       null,
        expectedValueEur: null,
        needsReview:      false,
        rule:             'alert.inform',
        reason:           `${hit.matchedHours} hour(s) matched: the team is told; no customer is affected.`,
        inputs:           { matchedHours: hit.matchedHours, ...evidence },
    };
}

function none(rule: string, reason: string, inputs: Record<string, number>): Agent.Decision {
    return {
        label:            'none',
        confidence:       null,
        expectedValueEur: null,
        needsReview:      false,
        rule,
        reason,
        inputs,
    };
}

const formatPrice = (price: number | undefined) => (price === undefined ? 'a low price' : `${price.toFixed(1)} EUR/MWh on average`);
