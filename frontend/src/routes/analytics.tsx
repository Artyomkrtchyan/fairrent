import { createFileRoute } from "@tanstack/react-router";
import { apiMode } from "@/api/client";
import { ListingSnapshotAnalytics } from "@/components/ListingSnapshotAnalytics";
import { PageHeader, RateNote } from "@/components/ui-bits";

export const Route = createFileRoute("/analytics")({
  head: () => ({
    meta: [{ title: "Market analytics — FairRent" }],
  }),
  component: MarketAnalytics,
});

export function MarketAnalytics() {
  return (
    <main className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6">
      <PageHeader
        title="Market analytics"
        intro="Compare asking rents from the currently available rental listings."
        tag={apiMode === "mock"}
      />
      <ListingSnapshotAnalytics />
      <RateNote />
    </main>
  );
}
