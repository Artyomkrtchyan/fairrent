import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import fixtures from "../../../contracts/fixtures.json";
import type { getListingDetails } from "@/api/listings";
import { MarketAssessment } from "@/components/MarketAssessment";

type Estimate = NonNullable<Awaited<ReturnType<typeof getListingDetails>>["estimate"]>;

const example = fixtures.estimate.value as Estimate;

const insufficientExample = fixtures["estimate-insufficient"].value as Estimate;

// Test assessment content separately from currency preferences.
vi.mock("@/components/ui-bits", () => ({
  Money: ({ usd, suffix = "/mo" }: { usd: number; suffix?: string }) => (
    <span>
      {usd} USD {suffix}
    </span>
  ),

  RateNote: () => null,
}));

vi.mock("@/api/client", () => ({
  apiMode: "mock",
}));

afterEach(cleanup);

describe("market assessment", () => {
  it("shows the estimate, range and synthetic-data notice", () => {
    render(<MarketAssessment askingUsd={600} estimate={example} />);

    expect(
      screen.getByRole("heading", {
        name: "Market assessment",
      }),
    ).toBeInTheDocument();

    expect(screen.getAllByText(/600 USD/)).toHaveLength(2);
    expect(screen.getByText(/520 USD/)).toBeInTheDocument();
    expect(screen.getByText(/680 USD/)).toBeInTheDocument();

    expect(
      screen.getByText(/These figures do not demonstrate real model accuracy/),
    ).toBeInTheDocument();
  });

  it.each([
    [900, "above_range", "Above estimated range"],
    [400, "below_range", "Below estimated range"],
    [520, "within_range", "Within estimated range"],
    [680, "within_range", "Within estimated range"],
    [600, "within_range", "Within estimated range"],
  ] as const)(
    "compares asking rent %s against the displayed interval, ignoring the supplied status",
    (askingUsd, expectedStatus, label) => {
      const estimate: Estimate = {
        ...example,
        price_status: expectedStatus === "within_range" ? "above_range" : "within_range",
      };

      render(<MarketAssessment askingUsd={askingUsd} estimate={estimate} />);

      expect(screen.getByText(label)).toBeInTheDocument();
      const range = screen.getByRole("heading", { name: "Prediction range" }).parentElement!;
      expect(within(range).getByText(/520 USD/)).toBeInTheDocument();
      expect(within(range).getByText(/680 USD/)).toBeInTheDocument();
    },
  );

  it.each([null, "", "   "])(
    "makes the comparison unavailable when calibration metadata is %s",
    (calibrationVersion) => {
      const estimate: Estimate = {
        ...example,
        price_status: "within_range",
        ml_prediction_interval: {
          lower_bound_usd: 520,
          upper_bound_usd: 680,
          confidence_level: 0.95,
          interval_width_usd: 160,
          calibration_version: calibrationVersion,
        },
      };

      render(<MarketAssessment askingUsd={600} estimate={estimate} />);

      expect(screen.getByText("Comparison unavailable")).toBeInTheDocument();
      expect(screen.queryByText("Within estimated range")).not.toBeInTheDocument();
      expect(screen.queryByText(/520 USD/)).not.toBeInTheDocument();
      expect(screen.queryByText(/680 USD/)).not.toBeInTheDocument();
    },
  );

  it("handles an unavailable assessment without inventing a price", () => {
    render(<MarketAssessment askingUsd={600} estimate={null} />);

    expect(
      screen.getByText("No assessment is available for this listing yet."),
    ).toBeInTheDocument();

    expect(screen.getByText("Not available")).toBeInTheDocument();

    expect(
      screen.getByText("No supported property prediction range is available."),
    ).toBeInTheDocument();
  });

  it("explains insufficient data and an area reference", () => {
    render(<MarketAssessment askingUsd={600} estimate={insufficientExample} />);

    expect(screen.getByText("Comparison unavailable")).toBeInTheDocument();

    expect(screen.getByText(/not a prediction for this particular apartment/)).toBeInTheDocument();

    expect(screen.getByText(insufficientExample.explanation)).toBeInTheDocument();

    expect(screen.queryByText(/Reported level:/)).not.toBeInTheDocument();
  });

  it("does not display a prediction range without calibration metadata", () => {
    const estimate: Estimate = {
      ...example,
      ml_prediction_interval: {
        lower_bound_usd: 520,
        upper_bound_usd: 680,
        confidence_level: 0.95,
        interval_width_usd: 160,
        calibration_version: null,
      },
    };

    render(<MarketAssessment askingUsd={600} estimate={estimate} />);

    expect(screen.queryByText(/520 USD/)).not.toBeInTheDocument();

    expect(
      screen.getByText("No supported property prediction range is available."),
    ).toBeInTheDocument();
  });

  it("does not use observed standard deviation as a prediction range", () => {
    const estimate: Estimate = {
      ...example,
      ml_prediction_interval: {
        lower_bound_usd: null,
        upper_bound_usd: null,
        confidence_level: null,
        interval_width_usd: null,
        calibration_version: null,
      },
    };

    render(<MarketAssessment askingUsd={600} estimate={estimate} />);

    expect(screen.queryByText(/500 USD/)).not.toBeInTheDocument();
    expect(screen.queryByText(/700 USD/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Reported level:/)).not.toBeInTheDocument();
  });

  it("shows missing asking rent without replacing it with zero", () => {
    render(<MarketAssessment askingUsd={null} estimate={example} />);

    expect(screen.getByText("Not available")).toBeInTheDocument();

    expect(screen.getByText("Comparison unavailable")).toBeInTheDocument();
  });

  it("warns when the assessment source is stale", () => {
    const estimate: Estimate = {
      ...example,
      freshness: {
        ...example.freshness,
        is_stale: true,
      },
    };

    render(<MarketAssessment askingUsd={600} estimate={estimate} />);

    expect(screen.getByText(/This assessment uses data marked as stale/)).toBeInTheDocument();
  });

  it("shows when individual factor explanations are missing", () => {
    render(<MarketAssessment askingUsd={600} estimate={example} />);

    expect(screen.getByText(/No individual factor explanations were supplied/)).toBeInTheDocument();
  });
});
