import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { apiMode } from "@/api/client";
import {
  ReviewApiError,
  updateReview,
  validateReviewDraft,
  type Review,
  type ReviewDecision,
  type ReviewUpdate,
} from "@/api/reviews";
import { useReviewerSession } from "@/lib/reviewer-session";

const decisions: { value: ReviewDecision; label: string }[] = [
  { value: "dismissed", label: "Dismiss signal" },
  { value: "needs_follow_up", label: "Needs follow-up" },
  { value: "confirmed_issue", label: "Confirmed issue" },
];

export function ReviewDecisionForm({
  review,
  onSaved,
  onConflict,
}: {
  review: Review;
  onSaved: (review: Review) => void;
  onConflict: () => Promise<void>;
}) {
  const session = useReviewerSession();
  const [status, setStatus] = useState<ReviewUpdate["status"]>(
    review.status === "pending" ? "in_review" : "resolved",
  );
  const [decision, setDecision] = useState<ReviewDecision | "">("");
  const [reason, setReason] = useState("");
  const [checked, setChecked] = useState(false);
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const submitted = useRef(false);
  const update: ReviewUpdate = {
    status,
    decision: status === "resolved" ? decision || null : null,
    reason,
    version: review.version,
  };
  const error = validateReviewDraft(update.status, update.decision, reason);
  const mutation = useMutation({
    mutationKey: ["review-decision", session.revision, review.id],
    mutationFn: () => updateReview(review.id, update, undefined, session.access),
    retry: false,
    onSuccess: onSaved,
    onError: async (failure) => {
      // A failed/aborted response can still follow a committed transaction.
      // Reload the server state before allowing another write; never retry blindly.
      setNeedsRefresh(true);
      if (failure instanceof ReviewApiError && failure.status === 409) {
        try {
          await onConflict();
        } catch {
          /* The case query displays its refresh error. */
        }
      }
    },
    onSettled: () => {
      submitted.current = false;
    },
  });

  if (review.status === "resolved")
    return (
      <section className="card-surface p-5">
        <h2 className="text-lg font-semibold">Decision</h2>
        <p className="mt-2 text-sm">This case is resolved and cannot be changed.</p>
      </section>
    );

  return (
    <section className="card-surface p-5">
      <h2 className="text-lg font-semibold">
        {apiMode === "mock" ? "Decision draft" : "Review decision"}
      </h2>
      <form
        className="mt-4 space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          setChecked(true);
          if (error || apiMode !== "real" || !session.access || needsRefresh || submitted.current)
            return;
          submitted.current = true;
          mutation.mutate();
        }}
      >
        <fieldset disabled={mutation.isPending || needsRefresh} className="space-y-4">
          <label className="block text-sm font-semibold">
            Next status
            <select
              className="mt-1 w-full rounded-md border bg-card p-2"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value as ReviewUpdate["status"]);
                setChecked(false);
              }}
            >
              {review.status === "pending" && <option value="in_review">In review</option>}
              <option value="resolved">Resolved</option>
            </select>
          </label>
          {status === "resolved" && (
            <label className="block text-sm font-semibold">
              Decision
              <select
                className="mt-1 w-full rounded-md border bg-card p-2"
                value={decision}
                onChange={(event) => {
                  setDecision(event.target.value as ReviewDecision | "");
                  setChecked(false);
                }}
              >
                <option value="">Select a decision</option>
                {decisions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="block text-sm font-semibold">
            Required reason
            <textarea
              className="mt-1 w-full rounded-md border bg-card p-3"
              rows={4}
              maxLength={2000}
              value={reason}
              onChange={(event) => {
                setReason(event.target.value);
                setChecked(false);
              }}
              placeholder="Describe evidence checked and the reason for this decision"
            />
          </label>
          <p className="text-xs text-muted-foreground">{reason.length} / 2,000 characters</p>
          <button
            type="button"
            className="rounded-md border px-4 py-2 text-sm font-semibold"
            onClick={() => setChecked(true)}
          >
            Validate draft
          </button>
          {checked &&
            (error ? (
              <p role="alert" className="text-sm text-red-600">
                {error}
              </p>
            ) : (
              <p role="status" className="text-sm">
                Draft is valid. It has not been saved.
              </p>
            ))}
          <button
            type="submit"
            disabled={apiMode !== "real" || !session.access}
            className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50"
          >
            {mutation.isPending ? "Saving…" : "Save decision"}
          </button>
        </fieldset>
        {apiMode === "mock" && <p className="text-sm">Synthetic preview cannot save decisions.</p>}
        {mutation.isError && (
          <p role="alert" className="text-sm">
            {mutation.error.message}
          </p>
        )}
        {needsRefresh && (
          <button
            type="button"
            className="rounded-md border px-4 py-2"
            onClick={() => {
              void onConflict().catch(() => {});
            }}
          >
            Refresh case before deciding again
          </button>
        )}
      </form>
    </section>
  );
}
