import type { getListingDetails } from "@/api/listings";

type Estimate = NonNullable<Awaited<ReturnType<typeof getListingDetails>>["estimate"]>;

interface Props {
  factors: Estimate["feature_attributions"];
}

const featureLabels: Record<string, string> = {
  area_sqm: "Apartment area",
  rooms: "Number of rooms",
  renovation: "Renovation",
  building_type: "Building type",
  district: "District",
  distance_metro_m: "Distance to metro",
  distance_center_m: "Distance to city centre",
  distance_university_m: "Distance to university",
};

export function ValuationFactors({ factors }: Props) {
  return (
    <section aria-labelledby="valuation-factors-title">
      <h3 id="valuation-factors-title" className="font-sans text-sm font-bold">
        Factors behind the estimate
      </h3>

      {factors.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">
          No individual factor explanations were supplied. See the assessment explanation above.
        </p>
      ) : (
        <>
          <ul className="mt-3 space-y-3">
            {factors.map((factor, index) => (
              <li key={`${factor.feature}-${index}`} className="rounded-lg border p-3 text-sm">
                <p className="font-semibold">
                  {featureLabels[factor.feature] ?? factor.feature.replaceAll("_", " ")}
                </p>

                <p className="mt-1 text-muted-foreground">
                  Reported effect: {factor.impact_pct}%. Direction: {factor.direction}.
                </p>
              </li>
            ))}
          </ul>

          <p className="mt-3 text-xs text-muted-foreground">
            These values describe the model’s explanation. They are not fraud scores or guaranteed
            price changes, and should not be added together unless the model documentation
            explicitly supports that.
          </p>
        </>
      )}
    </section>
  );
}
