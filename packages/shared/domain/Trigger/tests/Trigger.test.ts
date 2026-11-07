import { describe, expect, it } from "vitest"
import { Dataset } from "../../Dataset"
import { Forecaster } from "../../Forecaster"
import { Trigger } from ".."

const runId = Forecaster.Run.createId()

const issueTs = new Date("2026-05-07T07:00:00Z")

/** A Saturday in May (UTC+3), at a local hour. */
const at = (localHour: number) => new Date(Date.UTC(2026, 4, 9, localHour - 3))

function prediction(localHour: number, pNearZero: number, quality: Dataset.Predictions.DataQuality = "ok"): Dataset.Predictions.Row {
    return {
        issue_ts:      issueTs,
        target_ts_utc: at(localHour),
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

const forecastHour = (row: Dataset.Predictions.Row): Trigger.Check.Hour => ({
    at:     row.target_ts_utc,
    values: { predictions: Trigger.Check.toValues(row, Dataset.Predictions.compute(row, null)) },
})

/** The run's update: the Saturday's hours. */
const update: Dataset.Update = {
    dataset: "predictions",
    start:   at(0),
    end:     at(24),
    runId,
}

const checkOf = (hours: Trigger.Check.Hour[]): Trigger.Check => ({
    cause: { type: "dataset", update },
    runId,
    hours,
})

const zeroCostWindow = Trigger.Schema.parse({
    id:              Trigger.createId(),
    name:            "Zero-cost window",
    description:     "Midday hours likely to clear near zero: candidate free hours.",
    enabled:         true,
    on:              { type: "dataset", dataset: "predictions" },
    match:           "all",
    conditions: [
        { dataset: "predictions", column: "p_near_zero",  operator: ">=",      value: 0.75 },
        { dataset: "predictions", column: "local_hour",   operator: "between", value: [9, 17] },
        { dataset: "predictions", column: "data_quality", operator: "==",      value: "ok" },
    ],
    grouping:        { type: "window", minHours: 2, maxHours: 6 },
    cooldownMinutes: 1440,
})

describe("Trigger.Schema", () => {

    it("rejects a value that doesn't fit its operator", () => {
        const result = Trigger.Schema.safeParse({
            ...zeroCostWindow,
            conditions: [{ dataset: "predictions", column: "local_hour", operator: "between", value: 9 }],
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
        const hours: Trigger.Check.Hour[] = []

        for (let h = 7; h <= 18; h++) {
            let p = 0.2

            if (h >= 9 && h <= 13)
                p = 0.85

            hours.push(forecastHour(prediction(h, p)))
        }

        const hits = Trigger.evaluate(zeroCostWindow, checkOf(hours))

        expect(hits).toHaveLength(1)
        expect(hits[0].matchedHours).toBe(5)
        expect(hits[0].window?.key).toBe("20260509T0600Z-20260509T1100Z")
        expect(hits[0].evidence["predictions.p_near_zero.min"]).toBe(0.85)
    })

    it("doesn't hold on a column the hour doesn't have", () => {
        const unknown = Trigger.Schema.parse({
            ...zeroCostWindow,
            conditions: [{ dataset: "predictions", column: "not_a_column", operator: ">", value: 0 }],
        })

        expect(Trigger.evaluate(unknown, checkOf([forecastHour(prediction(10, 0.9))]))).toEqual([])
    })

    it("counts text values for run grouping", () => {
        const degraded = Trigger.Schema.parse({
            ...zeroCostWindow,
            name:       "Degraded inputs",
            conditions: [{ dataset: "predictions", column: "data_quality", operator: "in", value: ["degraded", "failed"] }],
            grouping:   { type: "run" },
        })

        const hours = [prediction(10, 0.9, "degraded"), prediction(11, 0.9, "degraded"), prediction(12, 0.9)].map(forecastHour)
        const hits = Trigger.evaluate(degraded, checkOf(hours))

        expect(hits).toHaveLength(1)
        expect(hits[0].window).toBeNull()
        expect(hits[0].evidence).toEqual({ "predictions.data_quality=degraded": 2 })
    })

    it("joins conditions on different datasets by hour: a forecast the auction proved wrong", () => {
        const forecastMiss = Trigger.Schema.parse({
            ...zeroCostWindow,
            name:       "Forecast miss",
            on:         { type: "dataset", dataset: "prices" },
            conditions: [
                { dataset: "predictions", column: "p_near_zero", operator: ">=", value: 0.75 },
                { dataset: "prices",      column: "price_mean",  operator: ">",  value: 20 },
            ],
            grouping:   { type: "hour" },
        })

        const hour = (localHour: number, pNearZero: number, priceMean: number | null): Trigger.Check.Hour => {
            const forecast = forecastHour(prediction(localHour, pNearZero))

            if (priceMean !== null) {
                const price = {
                    ts_utc:     at(localHour),
                    price_mean: priceMean,
                    price_min:  priceMean - 5,
                    price_max:  priceMean + 5,
                }

                forecast.values.prices = Trigger.Check.toValues(price, Dataset.PricesHourly.compute(price))
            }

            return forecast
        }

        const hits = Trigger.evaluate(forecastMiss, {
            cause: { type: "dataset", update: { dataset: "prices", start: at(0), end: at(24), runId: null } },
            runId,
            hours: [hour(11, 0.9, 60), hour(12, 0.9, 10), hour(13, 0.9, null), hour(14, 0.3, 80)],
        })

        expect(hits).toHaveLength(1)
        expect(hits[0].evidence["prices.price_mean.max"]).toBe(60)
        expect(Trigger.Hit.getThreadId(hits[0])).toBe(`${forecastMiss.id}_${hits[0].window?.key}_prices_20260508T2100Z-20260509T2100Z`)
    })

    it("fires a scheduled trigger once, without hours", () => {
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
            hours: [],
        })

        expect(hits).toHaveLength(1)
        expect(Trigger.Hit.getThreadId(hits[0])).toBe(`${report.id}_run_schedule-${Date.parse("2026-05-11T05:00:00Z")}`)
    })
})
