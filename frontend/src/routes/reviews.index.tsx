import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiMode } from "@/api/client";
import { getReviews, type ReviewFilters, type ReviewStatus } from "@/api/reviews";
import { Money, PageHeader, RateNote } from "@/components/ui-bits";
import { ReviewerSession } from "@/components/ReviewerSession";
import { useReviewerSession } from "@/lib/reviewer-session";

export const Route = createFileRoute("/reviews/")({
  head: () => ({
    meta: [{ title: "Reviewer workspace — FairRent" }, { name: "robots", content: "noindex" }],
  }),
  component: Reviews,
});

const statuses: { value: ReviewStatus | ""; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "pending", label: "Pending" },
  { value: "in_review", label: "In review" },
  { value: "resolved", label: "Resolved" },
];
const inputClass = "mt-1 w-full rounded-md border bg-card px-3 py-2 text-sm";

function Reviews() {
  return (
    <ReviewerSession>
      <ReviewQueue />
    </ReviewerSession>
  );
}

export function ReviewQueue() {
  const session = useReviewerSession();
  const [status, setStatus] = useState<ReviewStatus | "">("");
  const [category, setCategory] = useState<"" | "price_anomaly" | "risk_evidence">("");
  const [page, setPage] = useState(1);
  const filters: ReviewFilters = {
    ...(status && { status }),
    ...(category && { category }),
    page,
    page_size: 20,
  };
  const query = useQuery({
    queryKey: ["review-queue", session.revision, apiMode, status, category, page],
    queryFn: ({ signal }) => getReviews(filters, signal, session.access),
    enabled: apiMode === "mock" || !!session.access,
    retry: false,
  });

  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-8 sm:px-6">
      <PageHeader
        title="Reviewer workspace"
        intro="Inspect signals as evidence, never as proof of fraud."
      />
      {apiMode === "mock" && (
        <p
          role="note"
          className="rounded-lg border border-above/40 bg-warn-banner p-4 text-sm text-warn-banner-foreground"
        >
          <strong>Synthetic preview.</strong> Cases are from the shared C01 contract fixture. No
          reviewer is signed in and decisions cannot be saved.
        </p>
      )}
      <section className="card-surface p-4" aria-label="Review queue filters">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-semibold">
            Status
            <select
              className={inputClass}
              value={status}
              onChange={(e) => {
                setStatus(e.target.value as ReviewStatus | "");
                setPage(1);
              }}
            >
              {statuses.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm font-semibold">
            Evidence category
            <select
              className={inputClass}
              value={category}
              onChange={(e) => {
                setCategory(e.target.value as typeof category);
                setPage(1);
              }}
            >
              <option value="">All categories</option>
              <option value="price_anomaly">Price anomaly</option>
              <option value="risk_evidence">Risk evidence</option>
            </select>
          </label>
        </div>
      </section>
      <RateNote />
      {query.isPending && <p role="status">Loading review cases…</p>}
      {query.isError && (
        <section role="alert" className="card-surface p-5">
          <h2 className="font-semibold">Review queue unavailable</h2>
          <p className="mt-2 text-sm">{query.error.message}</p>
          <button
            type="button"
            className="mt-3 rounded-md border px-4 py-2"
            onClick={() => void query.refetch()}
          >
            Retry
          </button>
        </section>
      )}
      {query.data && (
        <section aria-label="Review cases" className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {query.data.total} case(s) · page {query.data.page}
          </p>
          {query.data.items.length === 0 && (
            <p className="card-surface p-5">No cases match these filters.</p>
          )}
          <ul className="grid gap-3">
            {query.data.items.map((review) => (
              <li key={review.id}>
                <Link
                  to="/reviews/$id"
                  params={{ id: review.id }}
                  search={{ listing: review.listing_id }}
                  className="card-surface block p-4 hover:border-primary"
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-semibold">{review.listing.title || "Untitled listing"}</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {review.listing.district_id ?? "Unknown area"} · {review.signals.length}{" "}
                        signal(s) · updated {new Date(review.updated_at).toLocaleDateString()}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                      <span className="text-sm font-semibold">
                        {review.listing.price_monthly_normalized === null ? (
                          "Rent unavailable"
                        ) : (
                          <Money usd={review.listing.price_monthly_normalized} />
                        )}
                      </span>
                      <span className="rounded-md border px-3 py-1 text-sm">
                        {review.status.replace("_", " ")}
                      </span>
                    </div>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={page <= 1 || query.isFetching}
              onClick={() => setPage(page - 1)}
              className="rounded-md border px-3 py-2 disabled:opacity-50"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={!query.data.has_more || query.isFetching}
              onClick={() => setPage(page + 1)}
              className="rounded-md border px-3 py-2 disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </section>
      )}
    </main>
  );
}
