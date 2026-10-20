import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ListingPhoto } from "@/components/ListingPhoto";
import { LISTINGS } from "@/lib/data";
import { LISTING_PHOTOS } from "@/lib/photos";

describe("listing photos", () => {
  it("resolves every non-null thumbnail to a bundled demo image", () => {
    for (const l of LISTINGS) {
      if (l.thumbnailUrl) expect(LISTING_PHOTOS[l.thumbnailUrl], l.id).toBeTruthy();
    }
  });

  it("shows the placeholder when no demo image is assigned", () => {
    render(<ListingPhoto photoKey={null} title="2-room in Nor Nork, new build" />);
    expect(screen.getByRole("img", { name: /photo unavailable/i })).toBeInTheDocument();
  });

  it("labels demo photos as demo, not as photos of the property", () => {
    render(<ListingPhoto photoKey="demo-cascade" title="Bright 2-room near Cascade" />);
    expect(
      screen.getByRole("img", { name: /demo image, not a photo of the actual property/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Demo image")).toBeInTheDocument();
  });

  it("falls back to the placeholder when the image fails to load", () => {
    render(<ListingPhoto photoKey="demo-cascade" title="Bright 2-room near Cascade" />);
    fireEvent.error(screen.getByRole("img"));
    expect(screen.getByRole("img", { name: /photo unavailable/i })).toBeInTheDocument();
  });
});
