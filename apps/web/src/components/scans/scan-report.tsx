"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { Copy, CopyPlus, ScatterChart, FileWarning, Trash2, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { ApiError } from "@/lib/api-client";
import { useScan, useCleanScan, useDeleteScan } from "@/lib/queries";
import { formatDate } from "@/lib/utils";
import { ScanStatusBadge } from "./scan-status-badge";
import { Thumbnail } from "./thumbnail";
import type { DuplicateGroup, ScanReport } from "@fastdup-dataset-cleaning/shared";

function StatPill({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-md border border-border bg-muted/20 px-3 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="text-lg font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function GroupSection({
  title,
  icon: Icon,
  groups,
  urls,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  groups: DuplicateGroup[];
  urls: Record<string, string>;
}) {
  const flaggedTotal = groups.reduce((n, g) => n + g.flagged.length, 0);
  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5 flex flex-row items-center justify-between">
        <CardTitle className="card-title flex items-center gap-2">
          <Icon className="h-4 w-4" />
          {title}
        </CardTitle>
        <Badge variant="secondary">{flaggedTotal} to quarantine</Badge>
      </CardHeader>
      <CardContent className="p-5 space-y-6">
        {groups.length === 0 ? (
          <p className="text-sm text-muted-foreground">None found.</p>
        ) : (
          groups.map((g) => (
            <div key={g.group_id} className="space-y-2">
              <div className="text-xs text-muted-foreground">
                Group {g.group_id + 1} — {g.flagged.length + 1} images
                {g.score !== null && <> · similarity {g.score}</>}
              </div>
              <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
                <Thumbnail url={urls[g.keep]} alt={g.keep.split("/").pop() ?? g.keep} badge="keep" />
                {g.flagged.map((key) => (
                  <Thumbnail key={key} url={urls[key]} alt={key.split("/").pop() ?? key} badge="dup" />
                ))}
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

export function ScanReportView({ runId }: { runId: string }) {
  const router = useRouter();
  const { data: report, isLoading, error, refetch } = useScan(runId);
  const cleanScan = useCleanScan();
  const deleteScan = useDeleteScan();

  if (isLoading) {
    return <Skeleton className="h-64 w-full" />;
  }
  if (error) {
    if (error instanceof ApiError && error.isNotFound) {
      return (
        <EmptyState
          icon={FileWarning}
          title="Scan not found"
          description="This run may have been deleted."
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
  if (!report) return null;

  const r: ScanReport = report;

  const onClean = async () => {
    try {
      const res = await cleanScan.mutateAsync(runId);
      toast.success(
        res.already_cleaned ? "Already cleaned" : "Cleaning applied",
        { description: `${res.quarantined_count} files copied to quarantine/. Originals are untouched.` },
      );
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Cleaning failed";
      toast.error("Failed to apply cleaning", { description: msg });
    }
  };

  const onDelete = async () => {
    try {
      await deleteScan.mutateAsync(runId);
      toast.success("Run deleted");
      router.push("/scans");
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Delete failed";
      toast.error("Failed to delete run", { description: msg });
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="border-b border-border py-4 px-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <CardTitle className="card-title">{r.label || r.run_id}</CardTitle>
              <ScanStatusBadge status={r.status} />
              {r.cleaned && <Badge variant="secondary">cleaned</Badge>}
            </div>
            <div className="flex items-center gap-2">
              {r.status === "complete" && (
                <Button
                  size="sm"
                  onClick={onClean}
                  disabled={cleanScan.isPending || r.cleaned || r.issues_found === 0}
                >
                  <ShieldCheck className="h-3.5 w-3.5" />
                  {r.cleaned ? "Cleaned" : "Apply cleaning"}
                </Button>
              )}
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button size="sm" variant="outline" disabled={deleteScan.isPending}>
                    <Trash2 className="h-3.5 w-3.5" />
                    Delete
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete this run?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This removes only this run&apos;s report artifacts from B2
                      (the quality-reports/{r.run_id}/ prefix). Your dataset
                      images and any quarantined files are not affected.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction onClick={onDelete}>Delete run</AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-5 space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatPill label="Dataset" value={r.dataset} />
            <StatPill label="Sensitivity" value={r.sensitivity} />
            <StatPill label="Images" value={r.total_images} />
            <StatPill label="Issues" value={r.status === "complete" ? r.issues_found : "-"} />
          </div>
          <p className="text-xs text-muted-foreground">
            Started {formatDate(r.created_at)}
            {r.completed_at && <> · finished {formatDate(r.completed_at)}</>} ·{" "}
            <Link href={`/datasets/${r.dataset}`} className="hover:underline">
              view dataset gallery
            </Link>
          </p>
          {r.status === "running" && (
            <p className="text-sm text-muted-foreground">
              Scanning… this page updates automatically when the run finishes.
            </p>
          )}
          {r.status === "failed" && (
            <p className="text-sm text-[var(--destructive)]">
              Scan failed: {r.error ?? "unknown error"}
            </p>
          )}
        </CardContent>
      </Card>

      {r.status === "complete" && (
        <>
          {r.issues_found === 0 ? (
            <Card>
              <CardContent className="p-0">
                <EmptyState
                  icon={ShieldCheck}
                  title="No issues found"
                  description="fastdup found no duplicates, outliers, or broken files at this sensitivity."
                />
              </CardContent>
            </Card>
          ) : (
            <>
              <GroupSection title="Exact duplicates" icon={Copy} groups={r.duplicates} urls={r.preview_urls} />
              <GroupSection title="Near-duplicates" icon={CopyPlus} groups={r.near_duplicates} urls={r.preview_urls} />

              <Card>
                <CardHeader className="border-b border-border py-4 px-5 flex flex-row items-center justify-between">
                  <CardTitle className="card-title flex items-center gap-2">
                    <ScatterChart className="h-4 w-4" />
                    Outliers
                  </CardTitle>
                  <Badge variant="secondary">{r.outliers.length} to quarantine</Badge>
                </CardHeader>
                <CardContent className="p-5">
                  {r.outliers.length === 0 ? (
                    <p className="text-sm text-muted-foreground">None found.</p>
                  ) : (
                    <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
                      {r.outliers.map((o) => (
                        <Thumbnail key={o.key} url={r.preview_urls[o.key]} alt={o.filename} />
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="border-b border-border py-4 px-5 flex flex-row items-center justify-between">
                  <CardTitle className="card-title flex items-center gap-2">
                    <FileWarning className="h-4 w-4" />
                    Broken / corrupt files
                  </CardTitle>
                  <Badge variant="secondary">{r.broken.length} to quarantine</Badge>
                </CardHeader>
                <CardContent className="p-5">
                  {r.broken.length === 0 ? (
                    <p className="text-sm text-muted-foreground">None found.</p>
                  ) : (
                    <ul className="space-y-2 text-sm">
                      {r.broken.map((b) => (
                        <li key={b.key} className="flex items-center justify-between gap-3 border-b border-border/60 pb-2">
                          <span className="font-mono text-xs">{b.filename}</span>
                          <span className="text-xs text-muted-foreground truncate">{b.reason}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>
            </>
          )}
        </>
      )}
    </div>
  );
}
