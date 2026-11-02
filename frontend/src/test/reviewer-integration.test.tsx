import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import fixtures from "../../../contracts/fixtures.json";
import { api } from "@/api/client";
import { getReviews, updateReview, type Review, type ReviewerAccess } from "@/api/reviews";
import { ReviewerSessionProvider } from "@/lib/reviewer-session";
import { ReviewerSession } from "@/components/ReviewerSession";
import { ReviewCaseContent } from "@/routes/reviews.$id";

const settings = vi.hoisted(() => ({ baseUrl: "http://localhost:8000" }));

vi.mock("@/api/client", () => ({
  apiMode: "real",
  get apiBaseUrl() {
    return settings.baseUrl;
  },
  api: { GET: vi.fn(), PATCH: vi.fn() },
}));
vi.mock("@tanstack/react-router", async (original) => ({
  ...(await original<typeof import("@tanstack/react-router")>()),
  Link: ({ children }: { children: React.ReactNode }) => <a href="/reviews">{children}</a>,
}));
vi.mock("@/lib/prefs", () => ({
  usePrefs: () => ({ format: (usd: number) => `${usd} USD`, canUseAmd: false }),
}));

// Synthetic session value and evidence only; never a provisioned credential.
const token = "x".repeat(43);
let record: Review;
let client: QueryClient;
const get = vi.mocked(api.GET);
const patch = vi.mocked(api.PATCH);

function response(data: unknown, status = 200) {
  return {
    ...(status === 200 ? { data } : { error: data }),
    response: new Response(null, { status }),
  };
}

function renderCase() {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <ReviewerSessionProvider>
        <ReviewerSession>
          <ReviewCaseContent id={record.id} listingId={record.listing_id} />
        </ReviewerSession>
      </ReviewerSessionProvider>
    </QueryClientProvider>,
  );
}

async function connect() {
  fireEvent.change(screen.getByLabelText("Reviewer session token"), { target: { value: token } });
  fireEvent.click(screen.getByRole("button", { name: "Connect reviewer session" }));
  await screen.findByText(record.listing.title!);
}

beforeEach(() => {
  vi.clearAllMocks();
  settings.baseUrl = "http://localhost:8000";
  record = structuredClone(fixtures.reviews.value.items[0]) as Review;
  get.mockImplementation(
    async () =>
      response({ items: [record], total: 1, page: 1, page_size: 100, has_more: false }) as never,
  );
  patch.mockImplementation(async (_path, options) => {
    const update = options!.body!;
    record = {
      ...record,
      ...update,
      version: record.version + 1,
      history: [
        ...record.history,
        {
          status: update.status,
          decision: update.decision,
          reason: update.reason,
          actor_id: record.id,
          created_at: "2026-11-01T08:00:00Z",
        },
      ],
    };
    return response(record) as never;
  });
});
afterEach(() => {
  cleanup();
  client?.clear();
  vi.restoreAllMocks();
});

describe("C05/D07 session and decision integration", () => {
  it("rejects a non-HTTPS remote API before transmitting a session", async () => {
    settings.baseUrl = "http://example.invalid";
    renderCase();
    fireEvent.change(screen.getByLabelText("Reviewer session token"), { target: { value: token } });
    fireEvent.click(screen.getByRole("button", { name: "Connect reviewer session" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("require HTTPS");
    expect(get).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Reviewer session token")).toHaveValue("");
  });

  it.each([422, 503])(
    "requires a refresh after a %s write failure and never claims success",
    async (status) => {
      renderCase();
      await connect();
      patch.mockResolvedValue(response({}, status) as never);
      fireEvent.change(screen.getByLabelText("Required reason"), {
        target: { value: "Synthetic check" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Save decision" }));
      await screen.findByRole("button", { name: "Refresh case before deciding again" });
      expect(screen.getByRole("button", { name: "Save decision" })).toBeDisabled();
      expect(screen.queryByText(/Decision saved/)).not.toBeInTheDocument();
      expect(patch).toHaveBeenCalledTimes(1);
    },
  );

  it("does not confirm a response without the matching history event", async () => {
    const access: ReviewerAccess = { token, controller: new AbortController(), reject: vi.fn() };
    patch.mockResolvedValue(response({ ...record, version: 2, history: [] }) as never);
    await expect(
      updateReview(
        record.id,
        { status: "resolved", decision: "dismissed", reason: "Checked evidence", version: 1 },
        undefined,
        access,
      ),
    ).rejects.toMatchObject({ status: 502 });
  });

  it("reads, saves with the current version, and displays returned history without storing credentials", async () => {
    const storage = vi.spyOn(Storage.prototype, "setItem");
    renderCase();
    expect(get).not.toHaveBeenCalled();
    await connect();
    expect(get.mock.calls[0]?.[1]).toMatchObject({
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      redirect: "error",
      credentials: "omit",
    });
    fireEvent.change(screen.getByLabelText("Required reason"), {
      target: { value: "Checked synthetic evidence" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save decision" }));
    await screen.findByText("Decision saved. The case and history show the server response.");
    expect(patch.mock.calls[0]?.[1]?.body).toEqual({
      status: "in_review",
      decision: null,
      reason: "Checked synthetic evidence",
      version: 1,
    });
    expect(screen.getByText("Checked synthetic evidence")).toBeInTheDocument();
    expect(screen.getByLabelText("Next status")).toHaveValue("resolved");
    fireEvent.change(screen.getByLabelText("Decision"), { target: { value: "dismissed" } });
    fireEvent.change(screen.getByLabelText("Required reason"), {
      target: { value: "Resolution evidence checked" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save decision" }));
    await screen.findByText("This case is resolved and cannot be changed.");
    expect(patch.mock.calls[1]?.[1]?.body.version).toBe(2);
    expect(screen.getByText("Resolution evidence checked")).toBeInTheDocument();
    expect(storage).not.toHaveBeenCalled();
    expect(
      JSON.stringify(
        client
          .getQueryCache()
          .getAll()
          .map((query) => query.queryKey),
      ),
    ).not.toContain(token);
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(screen.queryByText("Resolution evidence checked")).not.toBeInTheDocument();
    expect(client.getQueryCache().getAll()).toHaveLength(0);
    expect(client.getMutationCache().getAll()).toHaveLength(0);
  });

  it.each([401, 403])("clears the session and private case data on %s", async (status) => {
    renderCase();
    await connect();
    const options = get.mock.calls[0]![1] as RequestInit;
    get.mockResolvedValue(response({}, status) as never);
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["review-case"] });
    });
    expect(await screen.findByLabelText("Reviewer session token")).toHaveValue("");
    expect(screen.queryByText(record.listing.title!)).not.toBeInTheDocument();
    expect(options.signal?.aborted).toBe(true);
    expect(client.getQueryCache().getAll()).toHaveLength(0);
  });

  it("refreshes a conflicting case and requires a new decision instead of retrying", async () => {
    renderCase();
    await connect();
    patch.mockImplementation(async () => {
      record = { ...record, status: "in_review", version: 2 };
      return response({}, 409) as never;
    });
    fireEvent.change(screen.getByLabelText("Required reason"), { target: { value: "Old draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Save decision" }));
    await screen.findByText(
      "The case changed. Review the refreshed evidence and enter a new decision.",
    );
    await waitFor(() => expect(screen.getByLabelText("Next status")).toHaveValue("resolved"));
    expect(screen.getByLabelText("Required reason")).toHaveValue("");
    expect(patch).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledTimes(2);
  });

  it("does not submit an empty reason and stops repeat submissions while saving", async () => {
    renderCase();
    await connect();
    fireEvent.click(screen.getByRole("button", { name: "Save decision" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("reason is required");
    expect(patch).not.toHaveBeenCalled();
    let complete!: (value: never) => void;
    patch.mockImplementation(
      () =>
        new Promise((resolve) => {
          complete = resolve;
        }),
    );
    fireEvent.change(screen.getByLabelText("Required reason"), {
      target: { value: "Checking evidence" },
    });
    const save = screen.getByRole("button", { name: "Save decision" });
    fireEvent.click(save);
    fireEvent.click(save);
    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    await act(async () =>
      complete(response({ ...record, status: "in_review", version: 2 }) as never),
    );
  });

  it("rejects unauthenticated requests and suppresses responses from an ended session", async () => {
    await expect(getReviews({})).rejects.toMatchObject({ status: 401 });
    expect(get).not.toHaveBeenCalled();
    const access: ReviewerAccess = { token, controller: new AbortController(), reject: vi.fn() };
    let finish!: (value: never) => void;
    patch.mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const pending = updateReview(
      record.id,
      { status: "resolved", decision: "dismissed", reason: "Checked evidence", version: 1 },
      undefined,
      access,
    );
    const rejection = expect(pending).rejects.toMatchObject({ name: "AbortError" });
    access.controller.abort();
    finish(response(record) as never);
    await rejection;
  });
});
