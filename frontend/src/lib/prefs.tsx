import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import Decimal from "decimal.js-light";
import { useExchangeRate } from "@/api/exchange-rate";
import { apiMode } from "@/api/client";

export type ThemePref = "system" | "light" | "dark";
export type Currency = "USD" | "AMD";

interface Prefs {
  theme: ThemePref;
  setTheme: (theme: ThemePref) => void;
  currency: Currency;
  setCurrency: (currency: Currency) => void;
  format: (usd: number) => string;
  canUseAmd: boolean;
  rateLoading: boolean;
  rateSource: string | null;
  rateEffectiveAt: string | null;
  amdPerUsd: number | null;
  syntheticRate: boolean;
}

const Ctx = createContext<Prefs | null>(null);

function isTheme(value: unknown): value is ThemePref {
  return value === "system" || value === "light" || value === "dark";
}

function isCurrency(value: unknown): value is Currency {
  return value === "USD" || value === "AMD";
}

function readPreference(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function savePreference(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Preferences still work in memory when storage is unavailable.
  }
}

function applyTheme(theme: ThemePref) {
  const dark =
    theme === "dark" ||
    (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);

  document.documentElement.classList.toggle("dark", dark);
}

function groupDigits(value: string): string {
  const [whole = "", fraction] = value.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");

  return fraction === undefined ? grouped : `${grouped}.${fraction}`;
}

export function formatMoney(
  usd: number,
  currency: Currency,
  amdPerUsd: number | null = null,
): string {
  if (!Number.isFinite(usd)) {
    return "Not available";
  }

  const hasRate = amdPerUsd !== null && Number.isFinite(amdPerUsd) && amdPerUsd > 0;

  if (currency === "AMD" && hasRate) {
    const amount = new Decimal(usd).times(amdPerUsd).toFixed(0, Decimal.ROUND_HALF_UP);

    return `${groupDigits(amount)} AMD`;
  }

  const amount = new Decimal(usd).toFixed(2, Decimal.ROUND_HALF_UP);

  return `${groupDigits(amount)} USD`;
}

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemePref>("system");

  const [preferredCurrency, setCurrencyState] = useState<Currency>("USD");

  const exchange = useExchangeRate();

  const canUseAmd = exchange.canConvert;

  // Never show AMD labels when conversion is unavailable.
  const currency: Currency = preferredCurrency === "AMD" && canUseAmd ? "AMD" : "USD";

  const amdPerUsd = canUseAmd ? (exchange.rate?.amd_per_usd ?? null) : null;

  useEffect(() => {
    const storedTheme = readPreference("fr-theme");
    const storedCurrency = readPreference("fr-currency");

    if (isTheme(storedTheme)) {
      setThemeState(storedTheme);
    }

    if (isCurrency(storedCurrency)) {
      setCurrencyState(storedCurrency);
    }

    const onStorage = (event: StorageEvent) => {
      if (event.key === "fr-theme") {
        setThemeState(isTheme(event.newValue) ? event.newValue : "system");
      }

      if (event.key === "fr-currency") {
        setCurrencyState(isCurrency(event.newValue) ? event.newValue : "USD");
      }
    };

    window.addEventListener("storage", onStorage);

    return () => {
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  useEffect(() => {
    applyTheme(theme);

    if (theme !== "system") {
      return;
    }

    const media = window.matchMedia("(prefers-color-scheme: dark)");

    const updateTheme = () => applyTheme("system");

    media.addEventListener("change", updateTheme);

    return () => {
      media.removeEventListener("change", updateTheme);
    };
  }, [theme]);

  const setTheme = useCallback((value: ThemePref) => {
    setThemeState(value);
    savePreference("fr-theme", value);
  }, []);

  const setCurrency = useCallback(
    (value: Currency) => {
      if (value === "AMD" && !canUseAmd) {
        return;
      }

      setCurrencyState(value);
      savePreference("fr-currency", value);
    },
    [canUseAmd],
  );

  const format = useCallback(
    (usd: number) => formatMoney(usd, currency, amdPerUsd),
    [currency, amdPerUsd],
  );

  return (
    <Ctx.Provider
      value={{
        theme,
        setTheme,
        currency,
        setCurrency,
        format,
        canUseAmd,
        rateLoading: exchange.isPending || exchange.isFetching,
        rateSource: exchange.rate?.source ?? null,
        rateEffectiveAt: exchange.rate?.effective_at ?? null,
        amdPerUsd,
        syntheticRate: apiMode === "mock",
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function usePrefs() {
  const value = useContext(Ctx);

  if (!value) {
    throw new Error("usePrefs must be used inside PrefsProvider.");
  }

  return value;
}

export const THEME_BOOT_SCRIPT = `
try {
  var theme = localStorage.getItem("fr-theme") || "system";
  var dark =
    theme === "dark" ||
    (
      theme === "system" &&
      matchMedia("(prefers-color-scheme: dark)").matches
    );
  document.documentElement.classList.toggle("dark", dark);
} catch {}
`;
