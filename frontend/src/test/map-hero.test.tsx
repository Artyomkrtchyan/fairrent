import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { MapHero } from "@/components/MapHero";

vi.mock("@/lib/prefs", () => ({ usePrefs: () => ({ format: (value: number) => `$${value}` }) }));

vi.mock("@/components/MapCanvas", () => ({
  MapCanvas: ({ expanded = false }: { expanded?: boolean }) => (
    <div data-testid={expanded ? "expanded-map" : "embedded-map"}>Map preview</div>
  ),
}));

beforeAll(() => {
  for (const method of ["showModal", "close"]) {
    if (!(method in HTMLDialogElement.prototype)) {
      Object.defineProperty(HTMLDialogElement.prototype, method, {
        configurable: true,
        writable: true,
        value() {},
      });
    }
  }
});

beforeEach(() => {
  // jsdom does not implement the native modal API; real-browser checks cover it.
  vi.spyOn(HTMLDialogElement.prototype, "showModal").mockImplementation(function (
    this: HTMLDialogElement,
  ) {
    this.setAttribute("open", "");
  });
  vi.spyOn(HTMLDialogElement.prototype, "close").mockImplementation(function (
    this: HTMLDialogElement,
  ) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("framed map introduction", () => {
  it("opens only with the Expand action and returns focus after Close", async () => {
    const scrollTo = vi.spyOn(window, "scrollTo");
    render(<MapHero />);
    fireEvent.click(await screen.findByTestId("embedded-map"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const trigger = screen.getByRole("button", { name: "Expand map" });
    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Explore Yerevan" });
    expect(within(dialog).getByTestId("expanded-map")).toBeInTheDocument();
    expect(document.body.style.overflow).toBe("hidden");
    fireEvent.click(within(dialog).getByRole("button", { name: "Close map" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.body.style.overflow).not.toBe("hidden");
    expect(trigger).toHaveFocus();
    expect(scrollTo).toHaveBeenCalledWith(expect.objectContaining({ behavior: "instant" }));
  });

  it("handles the native Escape/cancel event", () => {
    render(<MapHero />);
    fireEvent.click(screen.getByRole("button", { name: "Expand map" }));
    fireEvent(
      screen.getByRole("dialog"),
      new Event("cancel", { bubbles: false, cancelable: true }),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand map" })).toHaveFocus();
  });

  it("moves to the existing filters without changing the search URL", () => {
    const scrollIntoView = vi.fn();
    const target = document.createElement("div");
    target.id = "rental-catalogue";
    target.tabIndex = -1;
    target.scrollIntoView = scrollIntoView;
    document.body.append(target);
    const previousUrl = window.location.href;
    render(<MapHero />);
    fireEvent.click(screen.getByRole("link", { name: "Browse rentals" }));
    expect(target).toHaveFocus();
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
    expect(window.location.href).toBe(previousUrl);
    target.remove();
  });
});
