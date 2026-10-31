import type { components } from "./schema";
import fixtures from "../../../contracts/fixtures.json";
import { api, apiMode } from "./client";

export type Review = components["schemas"]["Review"];
export type ReviewUpdate = components["schemas"]["ReviewUpdate"];
export type ReviewStatus = Review["status"];
export type ReviewDecision = NonNullable<Review["decision"]>;

export type ReviewFilters = {
  status?: ReviewStatus;
  category?: "price_anomaly" | "risk_evidence";
  rule_id?: string;
  listing_id?: string;
  page?: number;
  page_size?: number;
};

export class ReviewApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ReviewApiError";
  }
}

export function validateReviewDraft(
  status: ReviewUpdate["status"],
  decision: ReviewUpdate["decision"],
  reason: string,
): string | null {
  if (!reason.trim()) return "A reason is required for every review action.";
  if (status === "resolved" && !decision) return "Choose a decision to resolve this case.";
  if (status === "in_review" && decision !== null)
    return "An in-review case cannot have a final decision.";
  return null;
}

const syntheticPage = fixtures.reviews.value;

export async function getReviews(filters: ReviewFilters, signal?: AbortSignal) {
  // Synthetic preview, not a session: no network request, no writes, no real reviewer identity.
  if (apiMode === "mock") {
    const items = (syntheticPage.items as Review[]).filter((review) =>
      (!filters.status || review.status === filters.status) &&
      (!filters.category || review.signals.some((s) => s.category === filters.category)) &&
      (!filters.rule_id || review.signals.some((s) => s.rule_id === filters.rule_id)) &&
      (!filters.listing_id || review.listing_id === filters.listing_id),
    );
    const page = filters.page ?? 1;
    const pageSize = filters.page_size ?? 20;
    return {
      items: items.slice((page - 1) * pageSize, page * pageSize),
      total: items.length,
      page,
      page_size: pageSize,
      has_more: page * pageSize < items.length,
    };
  }

  const { data, response, error } = await api.GET("/api/v1/reviews", {
    params: { query: filters },
    signal,
  });
  if (!data) {
    throw new ReviewApiError(
      response.status,
      response.status === 401
        ? "Reviewer authentication is required. Session provisioning is managed by the backend."
        : response.status === 403
          ? "This account is not authorized to review listings."
          : response.status === 503
            ? "The review service is unavailable."
            : error ? "Could not load reviewer cases." : "Reviewer response was empty.",
    );
  }
  return data;
}

// Deliberately not called by the UI until C05 session provisioning has an agreed
// integration path. Never simulate a successful write or persist bearer tokens.
export async function updateReview(id: string, update: ReviewUpdate, signal?: AbortSignal) {
  if (apiMode === "mock") {
    throw new ReviewApiError(503, "Synthetic preview cannot save decisions.");
  }
  const { data, response } = await api.PATCH("/api/v1/reviews/{id}", {
    params: { path: { id } },
    body: update,
    signal,
  });
  if (!data) {
    throw new ReviewApiError(
      response.status,
      response.status === 409
        ? "The case changed since it was loaded. Refresh before reviewing again."
        : response.status === 401
          ? "Reviewer session is missing or expired."
          : response.status === 403
            ? "Reviewer permission is required."
            : "Decision could not be saved.",
    );
  }
  return data;
}
