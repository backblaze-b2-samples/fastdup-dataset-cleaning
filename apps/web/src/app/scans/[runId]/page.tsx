import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { ScanReportView } from "@/components/scans/scan-report";

export default async function ScanDetailPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5">
        <Link
          href="/scans"
          className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-3 w-3" />
          All scans
        </Link>
        <h1 className="page-title mt-2">Scan report</h1>
      </div>
      <div className="animate-fade-in-up stagger-2">
        <ScanReportView runId={runId} />
      </div>
    </div>
  );
}
