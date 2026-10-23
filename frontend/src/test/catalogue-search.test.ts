import { describe, expect, it } from "vitest";
import { parseCatalogueSearch } from "@/lib/catalogue-search";

describe("catalogue search", () => {
  it("uses defaults when the link has no search choices", () => {
    expect(parseCatalogueSearch({})).toEqual({
      page: 1,
      page_size: 20,
      sort: "newest",
      status: "active",
    });
  });

  it("reads filters, sorting and page numbers from a link", () => {
    expect(
      parseCatalogueSearch({
        district_id: "kentron",
        price_min: "300",
        price_max: "800",
        rooms: "2",
        area_min: "40",
        area_max: "90",
        page: "3",
        page_size: "10",
        sort: "price_asc",
      }),
    ).toEqual({
      district_id: "kentron",
      price_min: 300,
      price_max: 800,
      rooms: 2,
      area_min: 40,
      area_max: 90,
      page: 3,
      page_size: 10,
      sort: "price_asc",
      status: "active",
    });
  });

  it("ignores incorrect values", () => {
    expect(
      parseCatalogueSearch({
        page: "-1",
        page_size: "500",
        sort: "unknown",
        rooms: "2.5",
        price_min: "hello",
        area_min: "0",
        district_id: " ",
      }),
    ).toEqual({
      page: 1,
      page_size: 20,
      sort: "newest",
      status: "active",
    });
  });

  it("removes ranges where the minimum is above the maximum", () => {
    const search = parseCatalogueSearch({
      price_min: "900",
      price_max: "400",
      area_min: "100",
      area_max: "50",
    });

    expect(search.price_min).toBeUndefined();
    expect(search.price_max).toBeUndefined();
    expect(search.area_min).toBeUndefined();
    expect(search.area_max).toBeUndefined();
  });

  it("allows zero rent and an exact room count", () => {
    const search = parseCatalogueSearch({
      price_min: "0",
      rooms: "4",
    });

    expect(search.price_min).toBe(0);
    expect(search.rooms).toBe(4);
  });

  it("rejects non-finite numbers and repeated values", () => {
    const search = parseCatalogueSearch({
      price_max: "Infinity",
      rooms: ["1", "2"],
      page: "1.5",
    });

    expect(search.price_max).toBeUndefined();
    expect(search.rooms).toBeUndefined();
    expect(search.page).toBe(1);
  });

  it("keeps an inactive-listing search when requested", () => {
    expect(parseCatalogueSearch({ status: "inactive" }).status).toBe("inactive");
  });
});
