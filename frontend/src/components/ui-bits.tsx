import type { ReactNode } from "react";
import { STATUS_LABEL, type PriceStatus } from "@/lib/data";
import { usePrefs } from "@/lib/prefs";
import { cn } from "@/lib/utils";

const STATUS_CLASS: Record<PriceStatus, string> = {
  within: "bg-within-soft text-within border-within/40",
  above: "bg-above-soft text-above border-above/40",
  below: "bg-below-soft text-below border-below/40",
  unavailable: "bg-neutral-soft text-neutral border-neutral/30",
};
const STATUS_ICON: Record<PriceStatus, string> = {
  within: "✓",
  above: "▲",
  below: "▼",
  unavailable: "–",
};

export function StatusBadge({ status, className }: { status: PriceStatus; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold",
        STATUS_CLASS[status],
        className,
      )}
    >
      <span aria-hidden>{STATUS_ICON[status]}</span>
      {STATUS_LABEL[status]}
    </span>
  );
}

export function SyntheticTag({ children = "Synthetic demo data" }: { children?: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-md bg-warn-banner px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-warn-banner-foreground">
      {children}
    </span>
  );
}

export function Money({ usd, suffix = "/mo" }: { usd: number; suffix?: string }) {
  const { format } = usePrefs();
  return (
    <span className="tabular-nums">
      {format(usd)}
      {suffix && <span className="text-muted-foreground text-[0.8em] font-normal"> {suffix}</span>}
    </span>
  );
}

export function RateNote() {
  const {
    currency,
    canUseAmd,
    rateLoading,
    rateSource,
    rateEffectiveAt,
    amdPerUsd,
    syntheticRate,
  } = usePrefs();

  if (!canUseAmd) {
    return (
      <p className="text-xs text-muted-foreground">
        {rateLoading
          ? "Loading exchange rate. Prices are currently shown in USD."
          : "AMD conversion is unavailable. Prices are shown in USD."}
      </p>
    );
  }

  if (currency !== "AMD") {
    return null;
  }

  return (
    <p className="text-xs text-muted-foreground">
      {syntheticRate ? "Synthetic example rate" : "Display exchange rate"}
      {": "}1 USD = {amdPerUsd} AMD. Source: {rateSource ?? "Not supplied"}. Effective:{" "}
      {rateEffectiveAt ?? "Not supplied"}.
      {syntheticRate && " This is not a live or official exchange rate."}
    </p>
  );
}

export function PageHeader({
  title,
  intro,
  tag = true,
}: {
  title: string;
  intro?: ReactNode;
  tag?: boolean;
}) {
  return (
    <div className="mb-6 space-y-2">
      {tag && <SyntheticTag />}
      <h1 className="text-3xl font-semibold sm:text-4xl">{title}</h1>
      {intro && <p className="max-w-3xl text-muted-foreground">{intro}</p>}
    </div>
  );
}
