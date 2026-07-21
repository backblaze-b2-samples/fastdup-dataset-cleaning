"use client";

import Link from "next/link";
import { Images, ArrowRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { useDatasets } from "@/lib/queries";

export function DatasetsList() {
  const { data: datasets = [], isLoading, error, refetch } = useDatasets();

  if (isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-28 w-full" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="p-0">
          <ErrorState error={error} onRetry={() => refetch()} />
        </CardContent>
      </Card>
    );
  }

  if (datasets.length === 0) {
    return (
      <Card>
        <CardContent className="p-0">
          <EmptyState
            icon={Images}
            title="No datasets yet"
            description="Datasets live under the datasets/ prefix in your bucket. Run the seed script to create the demo dataset (see README)."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {datasets.map((d) => (
        <Link key={d.name} href={`/datasets/${d.name}`} className="group">
          <Card className="card-hover h-full">
            <CardContent className="p-5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 font-semibold">
                  <Images className="h-4 w-4 text-muted-foreground" />
                  {d.name}
                </div>
                <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
              </div>
              <div className="mt-4 flex items-center gap-6 text-sm text-muted-foreground">
                <div>
                  <div className="stat-value text-xl">{d.image_count}</div>
                  <div className="text-xs">images</div>
                </div>
                <div>
                  <div className="stat-value text-xl">{d.size_human}</div>
                  <div className="text-xs">on B2</div>
                </div>
              </div>
            </CardContent>
          </Card>
        </Link>
      ))}
    </div>
  );
}
