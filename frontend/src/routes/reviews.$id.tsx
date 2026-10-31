import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiMode } from "@/api/client";
import { getReviews, validateReviewDraft, type ReviewDecision, type ReviewUpdate } from "@/api/reviews";
import { PageHeader } from "@/components/ui-bits";

export const Route = createFileRoute("/reviews/$id")({
  head: () => ({ meta: [{ title: "Review case — FairRent" }, { name: "robots", content: "noindex" }] }),
  component: ReviewCase,
});

const decisions: { value: ReviewDecision; label: string }[] = [
  { value: "dismissed", label: "Dismiss signal" },
  { value: "needs_follow_up", label: "Needs follow-up" },
  { value: "confirmed_issue", label: "Confirmed issue" },
];

function ReviewCase() {
  const { id } = Route.useParams();
  const [status, setStatus] = useState<ReviewUpdate["status"]>("in_review");
  const [decision, setDecision] = useState<ReviewDecision | "">("");
  const [reason, setReason] = useState("");
  const [checked, setChecked] = useState(false);
  const query = useQuery({
    queryKey: ["review-case", apiMode, id],
    queryFn: async ({ signal }) => {
      // C01 exposes a queue GET, not a standalone GET /reviews/{id}.
      // The listing_id filter is not a case-id filter; paginate rather than guessing an endpoint.
      let page = 1;
      while (page <= 50) {
        const result = await getReviews({ page, page_size: 100 }, signal);
        const review = result.items.find((item) => item.id === id);
        if (review) return review;
        if (!result.has_more) return null;
        page += 1;
      }
      throw new Error("Case was not found in the first 5,000 queue records. Refine the queue search.");
    },
    retry: false,
  });
  const review = query.data;
  const error = validateReviewDraft(status, status === "resolved" ? decision || null : null, reason);
  return (
    <main className="mx-auto max-w-4xl space-y-5 px-4 py-8 sm:px-6">
      <Link to="/reviews" className="text-sm font-semibold text-primary">← Review queue</Link>
      <PageHeader title="Review case" intro="Review evidence and prepare a reasoned decision." />
      {apiMode === "mock" && <p role="note" className="rounded-lg border border-above/40 bg-warn-banner p-4 text-sm text-warn-banner-foreground"><strong>Synthetic preview.</strong> Drafts stay in this browser view and are not saved.</p>}
      {query.isPending && <p role="status">Loading case…</p>}
      {query.isError && <div role="alert" className="card-surface p-5">{query.error.message}<button type="button" className="ml-3 underline" onClick={() => void query.refetch()}>Retry</button></div>}
      {query.isSuccess && !review && <p className="card-surface p-5">Case not found.</p>}
      {review && <>
        <section className="card-surface space-y-3 p-5">
          <h2 className="text-xl font-semibold">{review.listing.title ?? "Untitled listing"}</h2>
          <p className="text-sm">Status: <strong>{review.status.replace("_", " ")}</strong> · Version {review.version}</p>
          <p className="text-sm">District: {review.listing.district_id ?? "Unknown"} · Asking rent: {review.listing.price_monthly_normalized === null ? "Unavailable" : `$${review.listing.price_monthly_normalized} USD/month`}</p>
          <a href={review.listing.source_url} target="_blank" rel="noopener noreferrer" className="text-sm font-semibold text-primary underline">Original listing</a>
          <h3 className="font-semibold">Signal evidence</h3>
          {review.signals.length === 0 ? <p>No signals recorded.</p> : <ul className="space-y-3">{review.signals.map((signal) => <li key={signal.id} className="rounded-md border p-3 text-sm"><p className="font-semibold">{signal.category.replace("_", " ")} · {signal.rule_id}</p><p className="mt-1">{signal.explanation}</p><ul className="mt-2 list-disc pl-5">{signal.evidence.map((evidence, index) => <li key={index}>{evidence}</li>)}</ul></li>)}</ul>}
          <p className="text-xs text-muted-foreground">A price anomaly does not establish fraud. Evidence may be incomplete or outdated.</p>
        </section>
        <section className="card-surface p-5">
          <h2 className="text-lg font-semibold">Decision draft</h2>
          <p className="mt-1 text-sm text-muted-foreground">Uses existing C01 status, decision, reason and version fields. No action is submitted until an approved reviewer session is integrated.</p>
          <div className="mt-4 space-y-4">
            <label className="block text-sm font-semibold">Next status
              <select className="mt-1 w-full rounded-md border bg-card p-2" value={status} onChange={(e) => { setStatus(e.target.value as ReviewUpdate["status"]); setChecked(false); }}>
                <option value="in_review">In review</option><option value="resolved">Resolved</option>
              </select>
            </label>
            {status === "resolved" && <label className="block text-sm font-semibold">Decision
              <select className="mt-1 w-full rounded-md border bg-card p-2" value={decision} onChange={(e) => { setDecision(e.target.value as ReviewDecision | ""); setChecked(false); }}>
                <option value="">Select a decision</option>
                {decisions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>}
            <label className="block text-sm font-semibold">Required reason
              <textarea className="mt-1 w-full rounded-md border bg-card p-3" rows={4} value={reason} onChange={(e) => { setReason(e.target.value); setChecked(false); }} placeholder="Describe evidence checked and the reason for this decision" />
            </label>
            <button type="button" className="rounded-md border px-4 py-2 text-sm font-semibold" onClick={() => setChecked(true)}>Validate draft</button>
            {checked && (error ? <p role="alert" className="text-sm text-red-600">{error}</p> : <p role="status" className="text-sm">Draft is valid against the local form rules. It has not been saved. Case version: {review.version}.</p>)}
            <button type="button" disabled className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground opacity-50">Save decision — awaiting approved session integration</button>
          </div>
        </section>
        <section className="card-surface p-5">
          <h2 className="text-lg font-semibold">Review history</h2>
          {review.history.length === 0 ? <p className="mt-2 text-sm">No decision history yet.</p> : <ol className="mt-3 space-y-2">{review.history.map((event, index) => <li key={index} className="border-l-2 pl-3 text-sm"><strong>{event.status}</strong> {event.decision ?? ""} · {event.created_at}<p>{event.reason}</p></li>)}</ol>}
        </section>
      </>}
    </main>
  );
}
