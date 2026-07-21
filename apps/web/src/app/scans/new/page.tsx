import { NewScanForm } from "@/components/scans/new-scan-form";

export default function NewScanPage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5">
        <h1 className="page-title">New scan</h1>
        <p className="mt-1.5 max-w-prose text-sm text-muted-foreground">
          Configure a dataset quality scan. The scan runs locally on CPU with
          fastdup — no external API key required.
        </p>
      </div>
      <div className="animate-fade-in-up stagger-2 max-w-3xl">
        <NewScanForm />
      </div>
    </div>
  );
}
