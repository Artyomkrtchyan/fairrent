import type { components } from "./schema";
import fixtures from "../../../contracts/fixtures.json";
import { api, apiMode } from "./client";

export type Review = components["schemas"]["Review"];
export type ReviewUpdate = components["schemas"]["ReviewUpdate"];
export type ReviewStatus = Review["status"];
export type ReviewDecision = NonNullable<Review["decision"]>;

export interface ReviewerAccess {
  token: string;
  controller: AbortController;
  reject: (message: string) => void;
}

function requestOptions(access: ReviewerAccess | undefined, signal?: AbortSignal) {
  if (!access) throw new ReviewApiError(401, "Connect a reviewer session to continue.");
  access.controller.signal.throwIfAborted();
  return {
    headers: { Authorization: `Bearer ${access.token}` },
    signal: signal ? AbortSignal.any([signal, access.controller.signal]) : access.controller.signal,
    cache: "no-store" as const,
    credentials: "omit" as const,
    redirect: "error" as const,
  };
}

function checkSession(access: ReviewerAccess | undefined, status: number) {
  if (status === 401 || status === 403) {
    access?.reject(
      status === 401
        ? "Session expired or was revoked. Connect a new session."
        : "This session does not have reviewer access.",
    );
  }
}

export type ReviewFilters = {
  status?: ReviewStatus;
  category?: "price_anomaly" | "risk_evidence";
  rule_id?: string;
  listing_id?: string;
  page?: number;
  page_size?: number;
};

export class ReviewApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
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
  if (reason.length > 2000) return "The reason must be 2,000 characters or fewer.";
  if (status === "resolved" && !decision) return "Choose a decision to resolve this case.";
  if (status === "in_review" && decision !== null)
    return "An in-review case cannot have a final decision.";
  return null;
}

const syntheticPage = fixtures.reviews.value;

export async function getReviews(
  filters: ReviewFilters,
  signal?: AbortSignal,
  access?: ReviewerAccess,
) {
  // Synthetic preview, not a session: no network request, no writes, no real reviewer identity.
  if (apiMode === "mock") {
    const items = (syntheticPage.items as Review[]).filter(
      (review) =>
        (!filters.status || review.status === filters.status) &&
        (!(filters.category || filters.rule_id) ||
          review.signals.some(
            (s) =>
              (!filters.category || s.category === filters.category) &&
              (!filters.rule_id || s.rule_id === filters.rule_id),
          )) &&
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
    ...requestOptions(access, signal),
  });
  access?.controller.signal.throwIfAborted();
  if (response.status !== 200 || !data) {
    checkSession(access, response.status);
    throw new ReviewApiError(
      response.status,
      response.status === 401
        ? "Reviewer authentication is required. Session provisioning is managed by the backend."
        : response.status === 403
          ? "This account is not authorized to review listings."
          : response.status === 503
            ? "The review service is unavailable."
            : error
              ? "Could not load reviewer cases."
              : "Reviewer response was empty.",
    );
  }
  return data;
}

export async function updateReview(
  id: string,
  update: ReviewUpdate,
  signal?: AbortSignal,
  access?: ReviewerAccess,
) {
  if (apiMode === "mock") {
    throw new ReviewApiError(503, "Synthetic preview cannot save decisions.");
  }
  const { data, response } = await api.PATCH("/api/v1/reviews/{id}", {
    params: { path: { id } },
    body: update,
    ...requestOptions(access, signal),
  });
  access?.controller.signal.throwIfAborted();
  if (response.status !== 200 || !data) {
    checkSession(access, response.status);
    throw new ReviewApiError(
      response.status,
      response.status === 409
        ? "The case changed since it was loaded. Refresh before reviewing again."
        : response.status === 401
          ? "Reviewer session is missing or expired."
          : response.status === 403
            ? "Reviewer permission is required."
            : response.status === 422
              ? "The server rejected the decision. Check its status, decision and reason."
              : response.status === 503
                ? "The review service is unavailable. Refresh the case before trying again."
                : "Decision could not be saved. Refresh the case to check its current state.",
    );
  }
  const event = data.history.at(-1);
  if (
    data.id !== id ||
    data.version <= update.version ||
    !event ||
    event.status !== update.status ||
    event.decision !== update.decision ||
    event.reason !== update.reason
  ) {
    throw new ReviewApiError(
      502,
      "The response did not confirm the decision and its history. Refresh the case before deciding again.",
    );
  }
  return data;
}
