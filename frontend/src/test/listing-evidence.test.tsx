import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import fixtures from "../../../contracts/fixtures.json";
import type { getListingDetails } from "@/api/listings";
import { ListingSource } from "@/components/ListingSource";
import { RiskEvidence } from "@/components/RiskEvidence";

type Detail = Awaited<ReturnType<typeof getListingDetails>>;

const detail = fixtures["listing-detail"].value as Detail;

vi.mock("@/api/client", () => ({
  apiMode: "mock",
}));

afterEach(cleanup);

describe("listing source", () => {
  it("opens a supported source URL safely", () => {
    render(<ListingSource listing={detail.listing} />);

    const link = screen.getByRole("link", {
      name: /Open demonstration source/,
    });

    expect(link).toHaveAttribute("href", detail.listing.source_url);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it.each([
    "javascript:alert(1)",
    "data:text/html,test",
    "not a URL",
    "https://user:password@example.org/listing",
  ])("does not create a link for %s", (sourceUrl) => {
    render(
      <ListingSource
        listing={{
          ...detail.listing,
          source_url: sourceUrl,
        }}
      />,
    );

    expect(screen.queryByRole("link")).not.toBeInTheDocument();

    expect(screen.getByText("No usable source link was supplied.")).toBeInTheDocument();
  });

  it("preserves the original price and currency", () => {
    render(<ListingSource listing={detail.listing} />);

    expect(screen.getByText("600.00 USD / month")).toBeInTheDocument();
  });
});

describe("risk evidence", () => {
  it("does not describe an empty signal list as proof of safety", () => {
    render(<RiskEvidence signals={[]} />);

    expect(screen.getByText(/This does not confirm that the listing is safe/)).toBeInTheDocument();
  });

  it("places price signals in their own section", () => {
    render(<RiskEvidence signals={detail.signals} />);

    expect(
      screen.getByRole("heading", {
        name: "Price comparisons",
      }),
    ).toBeInTheDocument();

    expect(screen.getByText(detail.signals[0]!.explanation)).toBeInTheDocument();
  });

  it("renders untrusted evidence as text, not HTML", () => {
    const signal = detail.signals[0]!;

    const text = '<img src="x" onerror="alert(1)">';

    const { container } = render(
      <RiskEvidence
        signals={[
          {
            ...signal,
            explanation: text,
            evidence: [text],
          },
        ]}
      />,
    );

    expect(screen.getAllByText(text)).toHaveLength(2);
    expect(container.querySelector("img")).toBeNull();
  });
});
