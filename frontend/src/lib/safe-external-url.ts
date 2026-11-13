/** Return a safe external link, never a javascript:, data: or credential-bearing URL. */
export function safeExternalUrl(value: string | null | undefined): string | null {
  if (!value || value.includes("\\\\")) return null;
  try {
    const url = new URL(value);
    if ((url.protocol !== "http:" && url.protocol !== "https:") || url.username || url.password) {
      return null;
    }
    return url.href;
  } catch {
    return null;
  }
}
