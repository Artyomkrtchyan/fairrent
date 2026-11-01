import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiMode } from "@/api/client";
import { getReviews } from "@/api/reviews";
import { Money, PageHeader, RateNote } from "@/components/ui-bits";
import { ReviewerSession } from "@/components/ReviewerSession";
import { ReviewDecisionForm } from "@/components/ReviewDecisionForm";
import { useReviewerSession } from "@/lib/reviewer-session";

export const Route = createFileRoute("/reviews/$id")({
  validateSearch: (search: Record<string, unknown>): { listing?: string } => {
    const listing = search["listing"];
    return typeof listing === "string" &&
      /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(listing)
      ? { listing }
      : {};
  },
  head: () => ({
    meta: [{ title: "Review case — FairRent" }, { name: "robots", content: "noindex" }],
  }),
  component: ReviewCase,
});

function ReviewCase() {
  const { id } = Route.useParams();
  const { listing } = Route.useSearch();
  return (
    <ReviewerSession>
      <ReviewCaseContent key={id} id={id} listingId={listing} />
    </ReviewerSession>
  );
}

export function ReviewCaseContent({
  id,
  listingId,
}: {
  id: string;
  listingId?: string | undefined;
}) {
  const session = useReviewerSession();
  const client = useQueryClient();
  const [notice, setNotice] = useState("");
  const [draftRevision, setDraftRevision] = useState(0);
  const query = useQuery({
    queryKey: ["review-case", session.revision, apiMode, id, listingId],
    queryFn: async ({ signal }) => {
      // C01 exposes a queue GET, not a standalone GET /reviews/{id}.
      // The listing_id filter is not a case-id filter; paginate rather than guessing an endpoint.
      let page = 1;
      while (page <= 50) {
        const result = await getReviews(
          { page, page_size: 100, ...(listingId ? { listing_id: listingId } : {}) },
          signal,
          session.access,
        );
        const review = result.items.find((item) => item.id === id);
        if (review) return review;
        if (!result.has_more) return null;
        page += 1;
      }
      throw new Error(
        "Case was not found in the first 5,000 queue records. Refine the queue search.",
      );
    },
    retry: false,
    enabled: apiMode === "mock" || !!session.access,
  });
  const review = query.data;
  return (
    <main className="mx-auto max-w-4xl space-y-5 px-4 py-8 sm:px-6">
      <Link to="/reviews" className="text-sm font-semibold text-primary">
        ← Review queue
      </Link>
      <PageHeader title="Review case" intro="Review evidence and prepare a reasoned decision." />
      {apiMode === "mock" && (
        <p
          role="note"
          className="rounded-lg border border-above/40 bg-warn-banner p-4 text-sm text-warn-banner-foreground"
        >
          <strong>Synthetic preview.</strong> Drafts stay in this browser view and are not saved.
        </p>
      )}
      <RateNote />
      {notice && <p role="status">{notice}</p>}
      {query.isPending && <p role="status">Loading case…</p>}
      {query.isError && (
        <div role="alert" className="card-surface p-5">
          {query.error.message}
          <button type="button" className="ml-3 underline" onClick={() => void query.refetch()}>
            Retry
          </button>
        </div>
      )}
      {query.isSuccess && !review && <p className="card-surface p-5">Case not found.</p>}
      {review && !query.isError && (
        <>
          <section className="card-surface space-y-3 p-5">
            <h2 className="text-xl font-semibold">{review.listing.title ?? "Untitled listing"}</h2>
            <p className="text-sm">
              Status: <strong>{review.status.replace("_", " ")}</strong> · Version {review.version}
            </p>
            <p className="text-sm">
              District: {review.listing.district_id ?? "Unknown"} · Asking rent:{" "}
              {review.listing.price_monthly_normalized === null ? (
                "Unavailable"
              ) : (
                <Money usd={review.listing.price_monthly_normalized} suffix="/month" />
              )}
            </p>
            <a
              href={review.listing.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm font-semibold text-primary underline"
            >
              Original listing
            </a>
            <h3 className="font-semibold">Signal evidence</h3>
            {review.signals.length === 0 ? (
              <p>No signals recorded.</p>
            ) : (
              <ul className="space-y-3">
                {review.signals.map((signal) => (
                  <li key={signal.id} className="rounded-md border p-3 text-sm">
                    <p className="font-semibold">
                      {signal.category.replace("_", " ")} · {signal.rule_id}
                    </p>
                    <p className="mt-1">{signal.explanation}</p>
                    <ul className="mt-2 list-disc pl-5">
                      {signal.evidence.map((evidence, index) => (
                        <li key={index}>{evidence}</li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
            <p className="text-xs text-muted-foreground">
              A price anomaly does not establish fraud. Evidence may be incomplete or outdated.
            </p>
          </section>
          <ReviewDecisionForm
            key={`${review.id}:${review.version}:${draftRevision}`}
            review={review}
            onSaved={(updated) => {
              client.setQueryData(
                ["review-case", session.revision, apiMode, id, listingId],
                updated,
              );
              void client.invalidateQueries({ queryKey: ["review-queue"] });
              setNotice("Decision saved. The case and history show the server response.");
            }}
            onConflict={async () => {
              setNotice(
                "The case changed. Review the refreshed evidence and enter a new decision.",
              );
              await query.refetch({ throwOnError: true });
              setDraftRevision((value) => value + 1);
            }}
          />
          <section className="card-surface p-5">
            <h2 className="text-lg font-semibold">Review history</h2>
            {review.history.length === 0 ? (
              <p className="mt-2 text-sm">No decision history yet.</p>
            ) : (
              <ol className="mt-3 space-y-2">
                {review.history.map((event, index) => (
                  <li key={index} className="border-l-2 pl-3 text-sm">
                    <strong>{event.status}</strong> {event.decision ?? ""} · {event.created_at}
                    <p>{event.reason}</p>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </>
      )}
    </main>
  );
}
