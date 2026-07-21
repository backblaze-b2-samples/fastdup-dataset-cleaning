"use client";

import Link from "next/link";
import { ScanSearch, ImageOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { ApiError } from "@/lib/api-client";
import { useDataset } from "@/lib/queries";
import { Thumbnail } from "@/components/scans/thumbnail";

export function DatasetGallery({ name }: { name: string }) {
  const { data, isLoading, error, refetch } = useDataset(name);

  if (isLoading) {
    return (
      <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
        {Array.from({ length: 12 }).map((_, i) => (
          <Skeleton key={i} className="aspect-square w-full" />
        ))}
      </div>
    );
  }

  if (error) {
    if (error instanceof ApiError && error.isNotFound) {
      return (
        <EmptyState
          icon={ImageOff}
          title="Dataset not found"
          description="This dataset has no images under datasets/<name>/raw/."
        />
      );
    }
    return (
      <Card>
        <CardContent className="p-0">
          <ErrorState error={error} onRetry={() => refetch()} />
        </CardContent>
      </Card>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <Badge variant="secondary">{data.image_count} images</Badge>
          {data.quarantined_count > 0 && (
            <Badge variant="outline">{data.quarantined_count} quarantined</Badge>
          )}
        </div>
        <Button asChild size="sm">
          <Link href="/scans/new">
            <ScanSearch className="h-3.5 w-3.5" />
            Scan this dataset
          </Link>
        </Button>
      </div>
      <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
        {data.images.map((img) => (
          <Thumbnail
            key={img.key}
            url={img.url}
            alt={img.filename}
            badge={img.quarantined ? "quarantined" : undefined}
          />
        ))}
      </div>
    </div>
  );
}
