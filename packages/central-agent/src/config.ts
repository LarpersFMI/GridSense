/**
 * The business numbers the agent decides with. Assumptions, stated: a pilot segment of customers, the evening price
 * the shifted consumption would otherwise be bought at. Tune them here, never in the rules.
 *
 * The thresholds (τ) come from the ML team's validation slot curve (reports/real/eval/classify_slots_val.csv: 2–6 h
 * blocks 09–18 where every hour has p ≥ τ): τ 0.8 → 80 % of slots hit, τ 0.7 → 71 %.
 */
export const AGENT_CONFIG = {

    /** Every hour of the window at or above this p_near_zero: the slot is Likely, announced on its own. */
    likelyMinP: 0.8,

    /** Every hour at or above this, but not all above likelyMinP: Possible — an operator decides. */
    possibleMinP: 0.7,

    /** MWh a segment shifts into each free hour (pilot assumption). */
    shiftedMwhPerHour: 12,

    /** Customers a slot is announced to: PPC Energie's 2026 "Energie Electrică Activă Zero" pilot (assumption). */
    pilotCustomers: 5_000,

    /** MWh those customers moved into one free-hours slot: the pilot's ~71 MWh over 6 intervals (assumption). */
    shiftedMwhPerSlot: 11.8,

    /** What that energy would cost in the evening peak, EUR/MWh, without a forecast's P50 to go by. */
    eveningPriceEur: 140,
} as const
