import { createFileRoute, Link } from "@tanstack/react-router";
import { Money, PageHeader, RateNote, StatusBadge } from "@/components/ui-bits";
import { ReviewPreviewBanner } from "@/components/ReviewPreviewBanner";
import { LISTINGS, priceStatus } from "@/lib/data";

export const Route = createFileRoute("/reviews/")({
  head: () => ({
    meta: [
      { title: "Reviewer workspace preview — FairRent" },
      {
        name: "description",
        content: "Preview of the deferred FairRent reviewer workspace. Not live.",
      },
      { property: "og:title", content: "Reviewer workspace preview — FairRent" },
      { property: "og:description", content: "Deferred feature preview with synthetic cases." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: Reviews,
});

export const REVIEW_QUEUE = LISTINGS.filter((l) => l.risks.length > 0);

function Reviews() {
  return (
    <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <PageHeader
        title="Reviewer workspace"
        intro="Listings flagged with risk evidence would appear here for human review."
      />
      <ReviewPreviewBanner />
      <RateNote />
      <ul className="grid gap-3">
        {REVIEW_QUEUE.map((l) => (
          <li key={l.id}>
            <Link
              to="/reviews/$id"
              params={{ id: l.id }}
              className="card-surface block p-4 hover:border-primary"
            >
              <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-3">
                <div className="min-w-0">
                  <p className="truncate font-bold">{l.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {l.risks.length} signal(s) · {l.district}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold">
                    <Money usd={l.askingUsd} />
                  </span>
                  <StatusBadge status={priceStatus(l)} />
                </div>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
