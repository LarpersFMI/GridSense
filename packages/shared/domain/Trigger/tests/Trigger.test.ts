import { describe, expect, it } from "vitest"
import { Dataset } from "../../Dataset"
import { Forecaster } from "../../Forecaster"
import { Trigger } from "../Trigger"

const runId = Forecaster.Run.createId()

const issueTs = new Date("2026-05-07T07:00:00Z")

/** A Saturday in May (UTC+3): local 09:00–14:00 cheap, the rest not. */
function predictionAt(localHour: number, pNearZero: number, quality: Dataset.Predictions.DataQuality = "ok"): Dataset.Predictions.Row {
    return {
        issue_ts:      issueTs,
        target_ts_utc: new Date(Date.UTC(2026, 4, 9, localHour - 3)),
        horizon_days:  2,
        p_cheap:       pNearZero / 2,
        p_near_zero:   pNearZero,
        price_p10:     -40,
        price_p50:     5,
        price_p90:     30,
        data_quality:  quality,
        top_features:  "ghi_forecast:+0.24",
    }
}

function contextOf(predictions: Dataset.Predictions.Row[]): Trigger.Context {
    const rows: Trigger.Row[] = []

    for (const prediction of predictions)
        rows.push(Trigger.Row.fromPrediction(prediction, null))

    return {
        cause: { type: "signal", signal: { type: "predictions.ready", runId } },
        runId,
        rows,
    }
}

const zeroCostWindow = Trigger.Schema.parse({
    id:              Trigger.createId(),
    name:            "Zero-cost window",
    description:     "Weekend-style midday hours likely to clear near zero: candidate free hours.",
    enabled:         true,
    on:              { type: "signal", signal: "predictions.ready" },
    match:           "all",
    conditions: [
        { column: "p_near_zero",  operator: ">=",      value: 0.75 },
        { column: "local_hour",   operator: "between", value: [9, 17] },
        { column: "data_quality", operator: "==",      value: "ok" },
    ],
    grouping:        { type: "window", minHours: 2, maxHours: 6 },
    cooldownMinutes: 1440,
})

describe("Trigger.Schema", () => {

    it("rejects a column the source doesn't have", () => {
        const result = Trigger.Schema.safeParse({
            ...zeroCostWindow,
            conditions: [{ column: "price_mean", operator: ">", value: 20 }],
        })

        expect(result.success).toBe(false)
    })

    it("rejects a number operator on a text column", () => {
        const result = Trigger.Schema.safeParse({
            ...zeroCostWindow,
            conditions: [{ column: "data_quality", operator: ">=", value: "ok" }],
        })

        expect(result.success).toBe(false)
    })

    it("rejects conditions on a scheduled trigger", () => {
        const result = Trigger.Schema.safeParse({
            ...zeroCostWindow,
            on: { type: "schedule", cron: "0 8 * * MON" },
        })

        expect(result.success).toBe(false)
    })
})

describe("Trigger.evaluate", () => {

    it("makes one hit per window of matching hours", () => {
        const predictions = []

        for (let h = 7; h <= 18; h++) {
            let p = 0.2

            if (h >= 9 && h <= 13)
                p = 0.85

            predictions.push(predictionAt(h, p))
        }

        const hits = Trigger.evaluate(zeroCostWindow, contextOf(predictions))

        expect(hits).toHaveLength(1)
        expect(hits[0].matchedHours).toBe(5)
        expect(hits[0].window?.key).toBe("20260509T0600Z-20260509T1100Z")
        expect(hits[0].evidence["p_near_zero.min"]).toBe(0.85)
    })

    it("leaves degraded hours out", () => {
        const predictions = [predictionAt(10, 0.9), predictionAt(11, 0.9, "degraded"), predictionAt(12, 0.9)]

        expect(Trigger.evaluate(zeroCostWindow, contextOf(predictions))).toEqual([])
    })

    it("counts text values for run grouping", () => {
        const dataQuality = Trigger.Schema.parse({
            ...zeroCostWindow,
            name:       "Degraded inputs",
            conditions: [{ column: "data_quality", operator: "in", value: ["degraded", "failed"] }],
            grouping:   { type: "run" },
        })

        const predictions = [predictionAt(10, 0.9, "degraded"), predictionAt(11, 0.9, "degraded"), predictionAt(12, 0.9)]
        const hits = Trigger.evaluate(dataQuality, contextOf(predictions))

        expect(hits).toHaveLength(1)
        expect(hits[0].window).toBeNull()
        expect(hits[0].evidence).toEqual({ "data_quality=degraded": 2 })
    })

    it("fires a scheduled trigger once, without rows", () => {
        const report = Trigger.Schema.parse({
            ...zeroCostWindow,
            name:       "Weekly report",
            on:         { type: "schedule", cron: "0 8 * * MON" },
            conditions: [],
            grouping:   { type: "run" },
        })

        const hits = Trigger.evaluate(report, {
            cause: { type: "schedule", firedAt: new Date("2026-05-11T05:00:00Z") },
            runId: null,
            rows:  [],
        })

        expect(hits).toHaveLength(1)
        expect(Trigger.Hit.getThreadId(hits[0])).toBe(`${report.id}_run_schedule-${Date.parse("2026-05-11T05:00:00Z")}`)
    })
})
