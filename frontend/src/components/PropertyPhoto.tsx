import { useState } from "react";
import { apiMode } from "@/api/client";

interface Props {
  url: string | null;
  title: string;
  gallery?: string[];
  card?: boolean;
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

export function PropertyPhoto({ url, title, gallery = [], card = false }: Props) {
  const sources = [
    ...new Set([url, ...gallery].map(safeImageUrl).filter((photo) => photo !== null)),
  ];
  const [selected, setSelected] = useState(0);
  const [failed, setFailed] = useState<string[]>([]);
  const source = sources[selected] ?? sources[0];
  const available = source && !failed.includes(source);

  if (card) {
    return (
      <div className="aspect-video bg-muted">
        {available ? (
          <img
            src={source}
            alt=""
            className="h-full w-full object-cover"
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={() => setFailed([source])}
          />
        ) : (
          <span className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Photo unavailable
          </span>
        )}
      </div>
    );
  }

  return (
    <figure className="card-surface mt-6 overflow-hidden">
      {available ? (
        <img
          src={source}
          alt={`Source photo for ${title}`}
          className="aspect-video max-h-96 w-full object-cover"
          referrerPolicy="no-referrer"
          decoding="async"
          onError={() => setFailed((previous) => [...previous, source])}
        />
      ) : (
        <div className="flex min-h-48 items-center justify-center p-8 text-center">
          <div>
            <p className="font-semibold">Photo unavailable</p>
            <p className="mt-2 text-sm text-muted-foreground">
              Property details remain available below.
            </p>
          </div>
        </div>
      )}
      {sources.length > 1 && (
        <div className="flex flex-wrap gap-2 p-3" role="group" aria-label="Listing photos">
          {sources.map((photo, index) => (
            <button
              key={photo}
              type="button"
              aria-label={`Photo ${index + 1}`}
              aria-pressed={index === selected}
              onClick={() => setSelected(index)}
              className="overflow-hidden rounded border aria-pressed:border-primary"
            >
              <img
                src={photo}
                alt=""
                className="h-12 w-16 object-cover"
                loading="lazy"
                referrerPolicy="no-referrer"
              />
            </button>
          ))}
        </div>
      )}
      {available && (
        <figcaption className="px-4 py-2 text-xs text-muted-foreground">
          {apiMode === "mock"
            ? "Synthetic example image; not a verified property photo."
            : "Image supplied by the listing source."}
        </figcaption>
      )}
    </figure>
  );
}
