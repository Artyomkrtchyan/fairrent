import type { getListingDetails } from "@/api/listings";

type DetailResponse = Awaited<ReturnType<typeof getListingDetails>>;

interface Props {
  signals: DetailResponse["signals"];
}

export function RiskEvidence({ signals }: Props) {
  const priceSignals = signals.filter((signal) => signal.category === "price_anomaly");

  const otherSignals = signals.filter((signal) => signal.category !== "price_anomaly");

  return (
    <section className="card-surface mt-6 p-5" aria-labelledby="risk-evidence-title">
      <h2 id="risk-evidence-title" className="text-xl font-semibold">
        Signals and evidence
      </h2>

      <p className="mt-2 text-sm text-muted-foreground">
        These signals identify information worth checking. They are not fraud verdicts. A high
        asking rent alone does not establish fraud.
      </p>

      {signals.length === 0 ? (
        <p className="mt-4 rounded-lg border p-4 text-sm">
          No signals were supplied for this listing. This does not confirm that the listing is safe.
        </p>
      ) : (
        <div className="mt-5 space-y-6">
          {priceSignals.length > 0 && (
            <SignalGroup
              title="Price comparisons"
              description="These signals concern asking-price differences."
              signals={priceSignals}
            />
          )}

          {otherSignals.length > 0 && (
            <SignalGroup
              title="Other evidence to review"
              description="Check the supplied evidence before drawing conclusions."
              signals={otherSignals}
            />
          )}
        </div>
      )}
    </section>
  );
}

function SignalGroup({
  title,
  description,
  signals,
}: {
  title: string;
  description: string;
  signals: DetailResponse["signals"];
}) {
  return (
    <div>
      <h3 className="font-sans text-base font-bold">{title}</h3>

      <p className="mt-1 text-sm text-muted-foreground">{description}</p>

      <ul className="mt-3 space-y-3">
        {signals.map((signal) => (
          <li key={signal.id} className="rounded-lg border p-4">
            <p className="text-sm font-semibold">{signal.explanation}</p>

            {signal.evidence.length > 0 && (
              <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">
                {signal.evidence.map((evidence, index) => (
                  <li key={`${signal.id}-${index}`}>{evidence}</li>
                ))}
              </ul>
            )}

            <details className="mt-4 text-xs">
              <summary className="cursor-pointer font-semibold">Signal details</summary>

              <dl className="mt-3 space-y-2 break-words">
                <div>
                  <dt className="text-muted-foreground">Rule</dt>
                  <dd>{signal.rule_id}</dd>
                </div>

                <div>
                  <dt className="text-muted-foreground">Rule version</dt>
                  <dd>{signal.rules_version}</dd>
                </div>

                <div>
                  <dt className="text-muted-foreground">Recorded</dt>
                  <dd>
                    <time dateTime={signal.created_at}>
                      {new Date(signal.created_at).toLocaleString("en-GB", {
                        timeZone: "Asia/Yerevan",
                      })}
                    </time>
                  </dd>
                </div>
              </dl>
            </details>
          </li>
        ))}
      </ul>
    </div>
  );
}
