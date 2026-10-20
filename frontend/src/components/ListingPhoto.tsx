import { useState } from "react";
import { LISTING_PHOTOS } from "@/lib/photos";
import { cn } from "@/lib/utils";

/**
 * Photo area for a synthetic listing. Shows the bundled demo image when one is
 * assigned, otherwise an architectural placeholder labeled "Photo unavailable".
 * A missing or broken image never hides the listing: it falls back to the
 * placeholder instead.
 */
export function ListingPhoto({
  photoKey,
  title,
  size = "card",
  priority = false,
  className,
}: {
  /** The listing's `thumbnailUrl` demo key, or null for the placeholder. */
  photoKey: string | null;
  title: string;
  size?: "card" | "detail";
  /** Eager-load the detail-page image; card thumbnails stay lazy. */
  priority?: boolean;
  className?: string;
}) {
  const src = LISTING_PHOTOS[photoKey ?? ""];
  const [broken, setBroken] = useState(false);
  const available = Boolean(src) && !broken;

  return (
    <figure
      className={cn(
        "relative w-full overflow-hidden bg-muted",
        size === "card" ? "aspect-[16/10]" : "aspect-[16/9] rounded-xl",
        className,
      )}
    >
      {available ? (
        <>
          <img
            src={src}
            alt={`Demo image, not a photo of the actual property: ${title}`}
            width={1024}
            height={640}
            loading={priority ? "eager" : "lazy"}
            onError={() => setBroken(true)}
            className="absolute inset-0 h-full w-full object-cover"
          />
          <figcaption className="absolute bottom-2 left-2 rounded-md bg-background/85 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-muted-foreground backdrop-blur-sm">
            Demo image
          </figcaption>
        </>
      ) : (
        <div
          role="img"
          aria-label={`Photo unavailable: ${title}`}
          className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-muted-foreground"
        >
          <svg
            aria-hidden
            viewBox="0 0 64 48"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="h-10 w-10"
          >
            <path d="M2 46h60" strokeLinecap="round" />
            <path d="M8 46V14l14-8 14 8v32" />
            <path d="M36 46V20h16v26" />
            <path
              d="M14 22h4M22 22h4M14 30h4M22 30h4M14 38h4M22 38h4M40 26h8M40 34h8"
              strokeLinecap="round"
            />
          </svg>
          <p className="text-xs font-semibold">Photo unavailable</p>
        </div>
      )}
    </figure>
  );
}
