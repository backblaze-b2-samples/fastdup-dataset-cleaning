import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { DatasetGallery } from "@/components/datasets/dataset-gallery";

export default async function DatasetDetailPage({
  params,
}: {
  params: Promise<{ name: string }>;
}) {
  const { name } = await params;
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5">
        <Link
          href="/datasets"
          className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-3 w-3" />
          All datasets
        </Link>
        <h1 className="page-title mt-2">{decodeURIComponent(name)}</h1>
        <p className="mt-1.5 max-w-prose text-sm text-muted-foreground">
          Images in <code>datasets/{decodeURIComponent(name)}/raw/</code>.
          Quarantined files are flagged.
        </p>
      </div>
      <div className="animate-fade-in-up stagger-2">
        <DatasetGallery name={decodeURIComponent(name)} />
      </div>
    </div>
  );
}
