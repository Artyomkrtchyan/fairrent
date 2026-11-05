import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ListingPhoto } from "@/components/ListingPhoto";
import { PropertyPhoto } from "@/components/PropertyPhoto";
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

it("switches source photos and keeps other photos accessible after an image fails", () => {
  const cover = "https://img.list.am/f/1/1.webp";
  const second = "https://img.list.am/f/2/2.webp";
  render(<PropertyPhoto url={cover} gallery={[cover, second]} title="Apartment" />);
  const mainPhoto = () => screen.getByRole("img", { name: "Source photo for Apartment" });
  expect(mainPhoto()).toHaveAttribute("src", cover);

  fireEvent.click(screen.getByRole("button", { name: "Photo 2" }));
  expect(mainPhoto()).toHaveAttribute("src", second);
  fireEvent.error(mainPhoto());
  expect(screen.getByText("Photo unavailable")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Photo 1" }));
  expect(mainPhoto()).toHaveAttribute("src", cover);
});
