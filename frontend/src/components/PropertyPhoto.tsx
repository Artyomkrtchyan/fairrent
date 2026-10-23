import { useState } from "react";
import { apiMode } from "@/api/client";

interface Props {
  url: string | null;
  title: string;
}

function safeImageUrl(value: string | null): string | null {
  if (!value) return null;

  try {
    const url = new URL(value);

    if ((url.protocol !== "https:" && url.protocol !== "http:") || url.username || url.password) {
      return null;
    }

    return url.href;
  } catch {
    return null;
  }
}

export function PropertyPhoto({ url, title }: Props) {
  const source = safeImageUrl(url);

  const [failedSource, setFailedSource] = useState<string | null>(null);

  if (!source || failedSource === source) {
    return (
      <div className="card-surface mt-6 flex min-h-48 items-center justify-center p-8 text-center">
        <div>
          <p className="font-semibold">Photo unavailable</p>

          <p className="mt-2 text-sm text-muted-foreground">
            Property details remain available below.
          </p>
        </div>
      </div>
    );
  }

  return (
    <figure className="card-surface mt-6 overflow-hidden">
      <img
        src={source}
        alt={`Source photo for ${title}`}
        className="aspect-video max-h-96 w-full object-cover"
        referrerPolicy="no-referrer"
        decoding="async"
        onError={() => setFailedSource(source)}
      />

      <figcaption className="px-4 py-2 text-xs text-muted-foreground">
        {apiMode === "mock"
          ? "Synthetic example image; not a verified property photo."
          : "Image supplied by the listing source."}
      </figcaption>
    </figure>
  );
}
