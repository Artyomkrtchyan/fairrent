import { describe, expect, it, vi } from "vitest";
import { validateReviewDraft } from "../api/reviews";

vi.mock("../api/client", () => ({
  apiMode: "mock",
  api: { GET: vi.fn(), PATCH: vi.fn() },
}));

describe("D07 review reason validation", () => {
  it("rejects empty or whitespace-only reasons", () => {
    expect(validateReviewDraft("in_review", null, "")).toMatch(/required/);
    expect(validateReviewDraft("in_review", null, "   ")).toMatch(/required/);
  });

  it("accepts 2,000 characters and rejects 2,001", () => {
    expect(validateReviewDraft("resolved", "dismissed", "x".repeat(2000))).toBeNull();
    expect(validateReviewDraft("resolved", "dismissed", "x".repeat(2001))).toMatch(/2,000/);
  });

  it("enforces the existing C01 status and decision combinations", () => {
    expect(validateReviewDraft("resolved", null, "Evidence reviewed")).toMatch(/decision/);
    expect(validateReviewDraft("in_review", "dismissed", "Evidence reviewed")).toMatch(/in-review/);
    expect(validateReviewDraft("in_review", null, "Evidence reviewed")).toBeNull();
  });
});
