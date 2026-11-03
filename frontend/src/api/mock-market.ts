import fixtures from "../../../contracts/fixtures.json";
import type { MarketIndex, MarketIndexPage } from "./market";

function validDate(value: string): boolean {
  return (
    /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    Number.isFinite(Date.parse(value)) &&
    new Date(value).toISOString().slice(0, 10) === value
  );
}

export function mockMarketPage(url: URL): MarketIndexPage | undefined {
  const params = url.searchParams;
  const allowed = ["district_id", "period_start", "period_end", "page", "page_size"];

  for (const key of params.keys()) {
    if (!allowed.includes(key) || params.getAll(key).length > 1) return;
  }

  const district = params.get("district_id");
  const start = params.get("period_start");
  const end = params.get("period_end");
  const page = Number(params.get("page") ?? 1);
  const pageSize = Number(params.get("page_size") ?? 20);

  if (
    district === "" ||
    (start !== null && !validDate(start)) ||
    (end !== null && !validDate(end)) ||
    (start !== null && end !== null && start > end) ||
    !Number.isSafeInteger(page) ||
    page < 1 ||
    !Number.isSafeInteger(pageSize) ||
    pageSize < 1 ||
    pageSize > 100
  )
    return;

  const source = fixtures["market-index"].value.items as MarketIndex[];

  const available = source
    .filter((item) => district === null || item.district_id === district)
    .sort(
      (a, b) =>
        a.period_start.localeCompare(b.period_start) || a.district_id.localeCompare(b.district_id),
    );

  const filtered = available.filter(
    (item) =>
      (start === null || item.period_start >= start) && (end === null || item.period_start <= end),
  );

  return {
    items: filtered.slice((page - 1) * pageSize, page * pageSize),
    page,
    page_size: pageSize,
    total: filtered.length,
    has_more: page * pageSize < filtered.length,
    available_from: available[0]?.period_start ?? null,
    available_to: available.at(-1)?.period_start ?? null,
  };
}
