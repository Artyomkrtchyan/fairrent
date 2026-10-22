import type { getListingDetails } from "@/api/listings";
import { apiMode } from "@/api/client";
import { Money, RateNote } from "@/components/ui-bits";

import { ValuationFactors } from "@/components/ValuationFactors";

type DetailResponse = Awaited<ReturnType<typeof getListingDetails>>;

interface Props {
  askingUsd: number | null;
  estimate: DetailResponse["estimate"];
}

const statusLabels = {
  within_range: "Within estimated range",
  above_range: "Above estimated range",
  below_range: "Below estimated range",
  insufficient_data: "Comparison unavailable",
};

const statusColors = {
  within_range: "bg-within-soft text-within",
  above_range: "bg-above-soft text-above",
  below_range: "bg-below-soft text-below",
  insufficient_data: "bg-neutral-soft text-neutral",
};

export function MarketAssessment({ askingUsd, estimate }: Props) {
  const assessment = estimate?.valuation_assessment;

  const isAreaReference = estimate?.kind === "area_reference";

  const insufficient = assessment?.assessment_status === "INSUFFICIENT_DATA_ABSTAIN";

  const estimatedUsd = !insufficient ? (assessment?.estimated_price_usd ?? null) : null;

  const status =
    !isAreaReference && !insufficient && askingUsd !== null && estimatedUsd !== null
      ? (estimate?.price_status ?? "insufficient_data")
      : "insufficient_data";

  const interval = estimate?.ml_prediction_interval;

  const lower = interval && "lower_bound_usd" in interval ? interval.lower_bound_usd : null;

  const upper = interval && "upper_bound_usd" in interval ? interval.upper_bound_usd : null;

  const confidence = interval && "confidence_level" in interval ? interval.confidence_level : null;

  const calibration =
    interval && "calibration_version" in interval ? interval.calibration_version : null;

  const validInterval =
    !isAreaReference &&
    !insufficient &&
    estimatedUsd !== null &&
    typeof lower === "number" &&
    Number.isFinite(lower) &&
    typeof upper === "number" &&
    Number.isFinite(upper) &&
    lower <= estimatedUsd &&
    estimatedUsd <= upper &&
    typeof confidence === "number" &&
    confidence > 0 &&
    confidence <= 1 &&
    typeof calibration === "string" &&
    calibration.trim() !== ""
      ? { lower, upper, confidence }
      : null;

  return (
    <section className="card-surface overflow-hidden" aria-labelledby="market-assessment-title">
      <div className="bg-hero p-5 text-hero-foreground">
        <p className="text-xs font-bold uppercase tracking-widest">Rental price insights</p>

        <h2 id="market-assessment-title" className="mt-2 text-2xl font-semibold">
          Market assessment
        </h2>

        <p className="mt-2 text-sm">
          A comparison with available market evidence, not a guarantee of value.
        </p>
      </div>

      <div className="space-y-5 p-5">
        {apiMode === "mock" && (
          <p className="rounded-md border p-3 text-xs">
            Synthetic example. These figures do not demonstrate real model accuracy.
          </p>
        )}

        <dl className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg bg-muted p-4">
            <dt className="text-sm text-muted-foreground">Asking rent</dt>

            <dd className="mt-2 text-xl font-bold text-heading">
              {askingUsd === null ? "Not available" : <Money usd={askingUsd} suffix="/ month" />}
            </dd>
          </div>

          <div className="rounded-lg bg-muted p-4">
            <dt className="text-sm text-muted-foreground">
              {isAreaReference ? "Area reference rent" : "Estimated rent"}
            </dt>

            <dd className="mt-2 text-xl font-bold text-heading">
              {estimatedUsd === null ? (
                "Not available"
              ) : (
                <Money usd={estimatedUsd} suffix="/ month" />
              )}
            </dd>
          </div>
        </dl>

        <RateNote />

        <span
          className={`inline-block rounded-full px-3 py-1 text-xs font-semibold ${statusColors[status]}`}
        >
          {statusLabels[status]}
        </span>

        {isAreaReference && (
          <p className="rounded-md border p-3 text-sm">
            This describes the area, not a prediction for this particular apartment.
          </p>
        )}

        <div>
          <h3 className="font-sans text-sm font-bold">What this means</h3>

          <p className="mt-2 text-sm">
            {estimate?.explanation ?? "No assessment is available for this listing yet."}
          </p>
        </div>
        {estimate && <ValuationFactors factors={estimate.feature_attributions} />}
        <div className="rounded-lg border p-4">
          <h3 className="font-sans text-sm font-bold">Prediction range</h3>

          {validInterval ? (
            <>
              <p className="mt-2 font-semibold">
                <Money usd={validInterval.lower} suffix="" />
                {" – "}
                <Money usd={validInterval.upper} suffix="/ month" />
              </p>

              <p className="mt-2 text-xs text-muted-foreground">
                Reported level: {Number((validInterval.confidence * 100).toFixed(1))}
                %. This range is separate from observed market price variation.
              </p>
            </>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">
              No supported property prediction range is available.
            </p>
          )}
        </div>

        {estimate && (
          <>
            <dl className="grid gap-4 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-muted-foreground">Comparable rentals</dt>
                <dd className="mt-1 font-semibold">
                  {estimate.observed_market_statistics.comparables_count}
                </dd>
              </div>

              <div>
                <dt className="text-muted-foreground">Source snapshot</dt>
                <dd className="mt-1 font-semibold">
                  {estimate.freshness.data_as_of === null
                    ? "Not available"
                    : new Date(estimate.freshness.data_as_of).toLocaleString("en-GB", {
                        timeZone: "Asia/Yerevan",
                      })}
                </dd>
              </div>
            </dl>

            {estimate.freshness.is_stale && (
              <p className="rounded-md border p-3 text-sm">
                This assessment uses data marked as stale. Check the source date before relying on
                it.
              </p>
            )}

            <details className="rounded-lg border p-4 text-sm">
              <summary className="cursor-pointer font-semibold">Model and data details</summary>

              <dl className="mt-3 space-y-3 break-words">
                <div>
                  <dt className="text-muted-foreground">Model version</dt>
                  <dd>{estimate.versions.model_version}</dd>
                </div>

                <div>
                  <dt className="text-muted-foreground">Rule version</dt>
                  <dd>{estimate.versions.rule_engine_version}</dd>
                </div>

                <div>
                  <dt className="text-muted-foreground">Search radius</dt>
                  <dd>{estimate.cohort.radius_m} metres</dd>
                </div>

                <div>
                  <dt className="text-muted-foreground">Observation period</dt>
                  <dd>
                    {estimate.cohort.period_start}
                    {" to "}
                    {estimate.cohort.period_end}
                  </dd>
                </div>
              </dl>
            </details>
          </>
        )}
      </div>
    </section>
  );
}
