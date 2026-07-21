import Image from "next/image";
import { ImageOff } from "lucide-react";

/**
 * Fixed-size image thumbnail rendered from a presigned B2 URL. `unoptimized`
 * because presigned URLs carry their own short-lived expiry (same rationale as
 * the file preview). Falls back to an icon tile when no URL is available.
 */
export function Thumbnail({
  url,
  alt,
  badge,
}: {
  url?: string | null;
  alt: string;
  badge?: string;
}) {
  return (
    <figure className="w-full">
      <div className="relative aspect-square w-full overflow-hidden rounded-md border border-border bg-muted/30">
        {url ? (
          <Image
            src={url}
            alt={alt}
            fill
            sizes="(max-width: 640px) 33vw, 128px"
            className="object-cover"
            unoptimized
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-muted-foreground">
            <ImageOff className="h-6 w-6" />
          </div>
        )}
        {badge && (
          <span className="absolute left-1 top-1 rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-medium text-white">
            {badge}
          </span>
        )}
      </div>
      <figcaption className="mt-1 truncate text-[11px] text-muted-foreground" title={alt}>
        {alt}
      </figcaption>
    </figure>
  );
}
