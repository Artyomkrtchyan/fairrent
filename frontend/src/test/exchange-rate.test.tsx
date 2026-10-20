import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import fixtures from "../../../contracts/fixtures.json";
import { useExchangeRate } from "../api/exchange-rate";

const { get } = vi.hoisted(() => ({
  get: vi.fn(),
}));

vi.mock("../api/client", () => ({
  apiMode: "mock",
  api: {
    GET: get,
  },
}));

let queryClient: QueryClient | undefined;

afterEach(() => {
  cleanup();
  queryClient?.clear();
  get.mockReset();
});

it("keeps a valid cached rate usable during a background refresh", async () => {
  const rate = fixtures["exchange-rate"].value;

  get.mockResolvedValueOnce({ data: rate });

  queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  const client = queryClient;

  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }

  const { result } = renderHook(() => useExchangeRate(), {
    wrapper: Wrapper,
  });

  await waitFor(() => {
    expect(result.current.canConvert).toBe(true);
  });

  let completeRefresh!: (value: { data: typeof rate }) => void;

  const pendingResponse = new Promise<{ data: typeof rate }>((resolve) => {
    completeRefresh = resolve;
  });

  get.mockReturnValueOnce(pendingResponse);

  let refresh!: Promise<void>;

  act(() => {
    refresh = client.refetchQueries({
      queryKey: ["exchange-rate", "mock"],
    });
  });

  await waitFor(() => {
    expect(result.current.isFetching).toBe(true);
  });

  // Prices must remain in AMD while a valid cached rate exists.
  expect(result.current.canConvert).toBe(true);
  expect(result.current.rate?.amd_per_usd).toBe(rate.amd_per_usd);

  await act(async () => {
    completeRefresh({ data: rate });
    await refresh;
  });

  await waitFor(() => {
    expect(result.current.isFetching).toBe(false);
  });

  expect(result.current.canConvert).toBe(true);
});
