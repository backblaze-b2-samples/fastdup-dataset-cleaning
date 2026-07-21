import Link from "next/link";
import { ScanSearch } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ScansList } from "@/components/scans/scans-list";

export default function ScansPage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in flex flex-wrap items-start justify-between gap-4 border-b border-border pb-5">
        <div className="min-w-0">
          <h1 className="page-title">Scans</h1>
          <p className="mt-1.5 max-w-prose text-sm text-muted-foreground">
            Curation runs — each is one fastdup scan over one dataset. Reports
            are stored as artifacts in B2 and survive restarts.
          </p>
        </div>
        <Button asChild size="sm" className="h-8 shrink-0">
          <Link href="/scans/new">
            <ScanSearch aria-hidden="true" className="h-3.5 w-3.5" />
            New scan
          </Link>
        </Button>
      </div>
      <div className="animate-fade-in-up stagger-2">
        <ScansList />
      </div>
    </div>
  );
}
