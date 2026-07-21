"use client";

import Link from "next/link";
import { ScanSearch } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { useScans } from "@/lib/queries";
import { formatDate } from "@/lib/utils";
import { ScanStatusBadge } from "./scan-status-badge";

export function ScansList() {
  const { data: scans = [], isLoading, error, refetch } = useScans();

  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-4 space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </CardContent>
      </Card>
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

  if (scans.length === 0) {
    return (
      <Card>
        <CardContent className="p-0">
          <EmptyState
            icon={ScanSearch}
            title="No scans yet"
            description="Start your first scan to find duplicates, outliers, and broken files in a dataset."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40 hover:bg-muted/40">
              <TableHead className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Run
              </TableHead>
              <TableHead className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Dataset
              </TableHead>
              <TableHead className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Sensitivity
              </TableHead>
              <TableHead className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Issues
              </TableHead>
              <TableHead className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Started
              </TableHead>
              <TableHead className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Status
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {scans.map((scan) => (
              <TableRow key={scan.run_id} className="table-row-hover">
                <TableCell className="font-medium">
                  <Link href={`/scans/${scan.run_id}`} className="hover:underline">
                    {scan.label || scan.run_id}
                  </Link>
                  {scan.cleaned && (
                    <Badge variant="secondary" className="ml-2 text-[10px]">
                      cleaned
                    </Badge>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">{scan.dataset}</TableCell>
                <TableCell className="text-muted-foreground capitalize">
                  {scan.sensitivity}
                </TableCell>
                <TableCell className="font-mono text-xs tabular-nums text-muted-foreground">
                  {scan.status === "complete" ? scan.issues_found : "-"}
                </TableCell>
                <TableCell className="text-muted-foreground whitespace-nowrap">
                  {formatDate(scan.created_at)}
                </TableCell>
                <TableCell>
                  <ScanStatusBadge status={scan.status} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
