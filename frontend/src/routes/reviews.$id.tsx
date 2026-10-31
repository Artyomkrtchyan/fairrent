import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { Money, PageHeader, RateNote, StatusBadge } from "@/components/ui-bits";
import { ReviewPreviewBanner } from "@/components/ReviewPreviewBanner";
import { getListing, priceStatus } from "@/lib/data";

export const Route = createFileRoute("/reviews/$id")({
  loader: ({ params }) => {
    const listing = getListing(params.id);
    if (!listing) throw notFound();
    return { listing };
  },
  head: () => ({
    meta: [
      { title: "Review case preview — FairRent" },
      { name: "description", content: "Preview of a deferred reviewer case. Not live." },
      { property: "og:title", content: "Review case preview — FairRent" },
      { property: "og:description", content: "Deferred feature preview with synthetic data." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: ReviewCase,
});

function ReviewCase() {
  const { listing: l } = Route.useLoaderData();
  return (
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <Link to="/reviews" className="text-sm font-semibold text-primary">
        ← Review queue
      </Link>
      <div className="mt-4">
        <PageHeader title={`Case ${l.id}`} intro={l.title} />
      </div>
      <ReviewPreviewBanner />
      <RateNote />
      <section className="card-surface p-5">
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge status={priceStatus(l)} />
          <span className="font-bold">
            <Money usd={l.askingUsd} />
          </span>
        </div>
        <h2 className="mt-4 text-lg font-semibold">Evidence</h2>
        <ul className="mt-2 list-disc pl-5 text-sm">
          {l.risks.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      </section>
      <form
        className="card-surface mt-4 space-y-3 p-5 opacity-70"
        aria-describedby="disabled-note"
        onSubmit={(e) => e.preventDefault()}
      >
        <fieldset disabled className="space-y-3">
          <legend className="text-lg font-semibold">Decision (disabled in preview)</legend>
          {["No action needed", "Request more information", "Hide listing"].map((o) => (
            <label key={o} className="flex items-center gap-2 text-sm">
              <input type="radio" name="decision" /> {o}
            </label>
          ))}
          <textarea
            className="w-full rounded-md border bg-card p-2 text-sm"
            rows={3}
            placeholder="Reviewer notes"
          />
          <button className="cursor-not-allowed rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground">
            Submit decision
          </button>
        </fieldset>
        <p id="disabled-note" className="text-xs text-muted-foreground">
          Decisions cannot be submitted — the reviewer workspace is deferred.
        </p>
      </form>
    </main>
  );
}
