import Link from "next/link";
import { ScanSearch } from "lucide-react";

import { Button } from "@/components/ui/button";
import { StatsCards } from "@/components/dashboard/stats-cards";
import { RecentScansTable } from "@/components/dashboard/recent-scans-table";
import { IssuesChart } from "@/components/dashboard/issues-chart";

export default function DashboardPage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-1.5">
            Dataset quality at a glance — issues found and files quarantined
            across your B2-hosted image datasets.
          </p>
        </div>
        <Button asChild size="sm" className="h-8">
          <Link href="/scans/new">
            <ScanSearch className="h-3.5 w-3.5" />
            New scan
          </Link>
        </Button>
      </div>
      <StatsCards />
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="animate-fade-in-up stagger-3">
          <IssuesChart />
        </div>
        <div className="animate-fade-in-up stagger-4">
          <RecentScansTable />
        </div>
      </div>
    </div>
  );
}
