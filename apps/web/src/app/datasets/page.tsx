import { DatasetsList } from "@/components/datasets/datasets-list";

export default function DatasetsPage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5">
        <h1 className="page-title">Datasets</h1>
        <p className="mt-1.5 max-w-prose text-sm text-muted-foreground">
          Image datasets stored under this app&apos;s <code>datasets/</code>{" "}
          prefix in B2. Open one to see its images and quality flags.
        </p>
      </div>
      <div className="animate-fade-in-up stagger-2">
        <DatasetsList />
      </div>
    </div>
  );
}
