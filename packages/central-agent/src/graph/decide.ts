import { Time, type Agent, type Trigger } from '@gridsense/shared/domain';
import { AGENT_CONFIG } from '../config';

const { Window } = Time;
type Window = Time.Window;

const HOUR_MS = 60 * 60_000;

/** One hour of the hit's window in the latest forecast: its p_near_zero, how many days ahead, data quality and P50. */
export interface Hourly {
    at:      Date
    p:       number
    horizon: number
    quality: string | null
    p50:     number | null
}

/**
 * The decision, per playbook — deterministic, on the model's numbers the hit carries (its evidence: each condition's
 * column, min / mean / max over the matched hours). The LLM never decides.
 */
export function decide(trigger: Trigger, hit: Trigger.Hit, slots: Agent.Slot[], hours: Hourly[]): Agent.Decision {
    const evidence = hit.evidence;
    const live = slots.filter((slot) => slot.status !== 'cancelled');

    switch (trigger.playbook) {
        case 'announce-slot':
            return decideAnnounce(hit, evidence, live, hours);
        case 'confirm-slot':
            return decideConfirm(hit, evidence, live);
        case 'cancel-slot':
            return decideCancel(hit, evidence, live);
        case 'alert':
            return decideAlert(hit, evidence);
    }
}

function decideAnnounce(hit: Trigger.Hit, evidence: Record<string, number>, live: Agent.Slot[], hours: Hourly[]): Agent.Decision {
    const minP = evidence['predictions.p_near_zero.min'];
    const meanP = evidence['predictions.p_near_zero.mean'];
    const inputs: Record<string, number> = { matchedHours: hit.matchedHours };

    if (hit.window === null || minP === undefined || meanP === undefined)
        return none('announce.needs-p', "The hit has no window, or its trigger doesn't read p_near_zero: nothing to announce.", inputs);

    inputs.minP = minP;
    inputs.meanP = meanP;

    // The hours no live slot covers yet. Without the hourly forecast, any live slot over the window counts as all of it.
    const open = hours.filter((hour) => !live.some((slot) => slot.start <= hour.at && hour.at < slot.end));

    if (live.length > 0 && open.length === 0)
        return none('announce.already', `Already announced over these hours (${live.map((slot) => slot.label).join(', ')}).`, inputs);

    // Too far out: an outlook. A later run brings these hours within reach, and that one decides.
    const horizon = hours.length === 0 ? null : Math.min(...hours.map((hour) => hour.horizon));

    if (horizon !== null) {
        inputs.horizonDays = horizon;

        if (horizon > AGENT_CONFIG.decideWithinDays)
            return none('announce.outlook', `D+${horizon}: an outlook for now. Slots are decided at D+${AGENT_CONFIG.decideWithinDays} or closer, on a later forecast.`, inputs);
    }

    // Partly announced: the hours still open are decided on their own.
    if (live.length > 0)
        return {
            ...none('announce.partly', `Part of these hours is already announced (${live.map((slot) => slot.label).join(', ')}); the ${open.length} hour(s) still open are decided on their own.`, inputs),
            followUps: stretches(open),
        };

    // Not every matched hour had data_quality = ok: the forecast is less sure.
    const okHours = evidence['predictions.data_quality=ok'];
    const isDegraded = okHours !== undefined && okHours < hit.matchedHours;
    const slotP50 = evidence['predictions.price_p50.mean'];

    if (slotP50 !== undefined)
        inputs.slotPriceP50 = slotP50;

    // The surest stretch: the longest run of hours all at or above likelyMinP (the whole window when every hour is).
    // Degraded inputs are never announced on their own.
    const core = isDegraded ? null : likelyCore(hit.window, minP, meanP, hours);

    if (core !== null) {
        const trimmed = core.window.key !== hit.window.key;
        const edges = stretches(hours.filter((hour) => hour.at < core.window.start || hour.at >= core.window.end));

        inputs.coreHours = core.window.hours;
        inputs.coreMinP = core.minP;

        return {
            label:            'likely',
            confidence:       core.meanP,
            needsReview:      false,
            rule:             trimmed ? 'announce.likely-core' : 'announce.likely',
            reason:           trimmed
                ? `${core.window.hours} of the ${hit.window.hours} hours have p_near_zero ≥ ${AGENT_CONFIG.likelyMinP} (lowest ${core.minP.toFixed(2)}): those are announced as Likely; the less sure hours around them go to an operator on their own.`
                : `Every hour has p_near_zero ≥ ${AGENT_CONFIG.likelyMinP} (lowest ${minP.toFixed(2)}): announced as Likely.`,
            inputs,
            window:           trimmed ? core.window : null,
            followUps:        edges,
        };
    }

    if (minP >= AGENT_CONFIG.possibleMinP)
        return {
            label:            'possible',
            confidence:       meanP,
            needsReview:      true,
            rule:             isDegraded ? 'announce.degraded' : 'announce.possible',
            reason:           isDegraded
                ? `Inputs were degraded for some hours: an operator decides (lowest p ${minP.toFixed(2)}).`
                : `Every hour has p_near_zero ≥ ${AGENT_CONFIG.possibleMinP}, and fewer than ${AGENT_CONFIG.likelyMinHours} hours in a row reach ${AGENT_CONFIG.likelyMinP} (lowest ${minP.toFixed(2)}): Possible, an operator decides.`,
            inputs,
            window:           null,
            followUps:        [],
        };

    return none('announce.too-unsure', `The lowest hour has p_near_zero ${minP.toFixed(2)}, under ${AGENT_CONFIG.possibleMinP}: not worth announcing.`, inputs);
}

/** Hours as the windows of consecutive ones they make up. */
const stretches = (hours: Hourly[]): Window[] => Window.group(hours, { minHours: 1, maxHours: 24 }).map((stretch) => Window.of(stretch));

/**
 * The longest run of consecutive hours, all at or above likelyMinP and at least likelyMinHours long; the earlier one on
 * a tie. Without the hourly forecast, the whole window when its lowest hour reaches likelyMinP.
 */
function likelyCore(window: Window, minP: number, meanP: number, hours: Hourly[]): { window: Window; minP: number; meanP: number } | null {
    if (hours.length === 0)
        return minP >= AGENT_CONFIG.likelyMinP ? { window, minP, meanP } : null;

    let best: Hourly[] = [];
    let run: Hourly[] = [];

    for (const hour of hours) {
        const follows = run.length > 0 && hour.at.getTime() - run[run.length - 1].at.getTime() === HOUR_MS;

        if (hour.p < AGENT_CONFIG.likelyMinP)
            run = [];
        else
            run = follows ? [...run, hour] : [hour];

        if (run.length > best.length)
            best = run;
    }

    if (best.length < AGENT_CONFIG.likelyMinHours)
        return null;

    return {
        window: Window.of(best),
        minP:   Math.min(...best.map((hour) => hour.p)),
        meanP:  best.reduce((sum, hour) => sum + hour.p, 0) / best.length,
    };
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
        needsReview:      false,
        rule:             live.length > 0 ? 'confirm.announced' : 'confirm.surprise',
        reason:           live.length > 0
            ? `The auction cleared these hours at ${formatPrice(price)}: the announced slot is confirmed.`
            : `The auction cleared these hours at ${formatPrice(price)} and nothing was announced: a surprise free slot.`,
        inputs,
        window:           null,
        followUps:        [],
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
        needsReview:      true,
        rule:             'cancel.announced',
        reason:           `${live.length} announced slot(s) overlap hours that no longer hold: cancelling reaches customers, so an admin approves.`,
        inputs,
        window:           null,
        followUps:        [],
    };
}

function decideAlert(hit: Trigger.Hit, evidence: Record<string, number>): Agent.Decision {
    return {
        label:            'alert',
        confidence:       null,
        needsReview:      false,
        rule:             'alert.inform',
        reason:           `${hit.matchedHours} hour(s) matched: the team is told; no customer is affected.`,
        inputs:           { matchedHours: hit.matchedHours, ...evidence },
        window:           null,
        followUps:        [],
    };
}

function none(rule: string, reason: string, inputs: Record<string, number>): Agent.Decision {
    return {
        label:            'none',
        confidence:       null,
        needsReview:      false,
        rule,
        reason,
        inputs,
        window:           null,
        followUps:        [],
    };
}

const formatPrice = (price: number | undefined) => (price === undefined ? 'a low price' : `${price.toFixed(1)} EUR/MWh on average`);
