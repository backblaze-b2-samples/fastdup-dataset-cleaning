"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  cleanScan,
  createScan,
  deleteFile,
  deleteScan,
  getCurationStats,
  getDataset,
  getDatasets,
  getFiles,
  getFileStats,
  getHealth,
  getIssueTypeCounts,
  getPreviewUrl,
  getScan,
  getScans,
  getUploadActivity,
} from "@/lib/api-client";
import type {
  FileMetadata,
  ScanReport,
  ScanRequest,
} from "@fastdup-dataset-cleaning/shared";

// Single source of truth for query keys. Keep these tightly scoped so that
// invalidating "files" doesn't blow away unrelated caches, and so an IDE
// "find usages" of `qk.files` reveals every consumer.
export const qk = {
  all: ["b2"] as const,
  files: (prefix?: string, limit?: number) =>
    [...qk.all, "files", prefix ?? "", limit ?? 100] as const,
  stats: () => [...qk.all, "stats"] as const,
  uploadActivity: (days: number) =>
    [...qk.all, "stats", "activity", days] as const,
  preview: (key: string) => [...qk.all, "preview", key] as const,
  health: () => [...qk.all, "health"] as const,
  datasets: () => [...qk.all, "datasets"] as const,
  dataset: (name: string) => [...qk.all, "datasets", name] as const,
  scans: () => [...qk.all, "scans"] as const,
  scan: (runId: string) => [...qk.all, "scans", runId] as const,
  curationStats: () => [...qk.all, "curation", "stats"] as const,
  issueCounts: () => [...qk.all, "curation", "issues"] as const,
};

export type Health = Awaited<ReturnType<typeof getHealth>>;

export function useFiles(prefix = "", limit = 100) {
  return useQuery<FileMetadata[], ApiError>({
    queryKey: qk.files(prefix, limit),
    queryFn: () => getFiles(prefix, limit),
  });
}

export function useFileStats() {
  return useQuery({
    queryKey: qk.stats(),
    queryFn: getFileStats,
  });
}

export function useUploadActivity(days = 7) {
  return useQuery({
    queryKey: qk.uploadActivity(days),
    queryFn: () => getUploadActivity(days),
  });
}

// Presigned preview URL — only fetched when `enabled` is true (e.g., when
// the dialog opens for a specific file). Kept short-lived (60s) because
// the URL itself has a presigned expiry and is cheap to regenerate.
export function usePreviewUrl(key: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: qk.preview(key ?? ""),
    queryFn: () => getPreviewUrl(key as string),
    enabled: enabled && !!key,
    staleTime: 60_000,
  });
}

// Health poll for the top-of-app B2 banner. `retry: false` and letting a
// failed fetch leave `data` undefined keeps a down API silent (the
// per-component ErrorState covers that); the banner only reacts to an up API
// reporting b2_connected: false. Polls every 60s and on window focus.
export function useHealth() {
  return useQuery<Health>({
    queryKey: qk.health(),
    queryFn: getHealth,
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: false,
  });
}

export function useDeleteFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (fileKey: string) => deleteFile(fileKey),
    // After delete, blow away every cached file list + stats. Cheap and
    // correct — the dashboard re-fetches lazily as components remount.
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.all });
    },
  });
}

// --- Curation ---

export function useDatasets() {
  return useQuery({ queryKey: qk.datasets(), queryFn: getDatasets });
}

export function useDataset(name: string | undefined) {
  return useQuery({
    queryKey: qk.dataset(name ?? ""),
    queryFn: () => getDataset(name as string),
    enabled: !!name,
  });
}

export function useScans() {
  return useQuery({ queryKey: qk.scans(), queryFn: getScans });
}

// A single run. While it's `running`, poll every 2s so the detail page
// advances to the completed report on its own.
export function useScan(runId: string | undefined) {
  return useQuery<ScanReport, ApiError>({
    queryKey: qk.scan(runId ?? ""),
    queryFn: () => getScan(runId as string),
    enabled: !!runId,
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 2000 : false,
  });
}

export function useCurationStats() {
  return useQuery({ queryKey: qk.curationStats(), queryFn: getCurationStats });
}

export function useIssueTypeCounts() {
  return useQuery({ queryKey: qk.issueCounts(), queryFn: getIssueTypeCounts });
}

export function useCreateScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ScanRequest) => createScan(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.scans() });
      qc.invalidateQueries({ queryKey: qk.curationStats() });
    },
  });
}

export function useCleanScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => cleanScan(runId),
    onSuccess: (_data, runId) => {
      qc.invalidateQueries({ queryKey: qk.scan(runId) });
      qc.invalidateQueries({ queryKey: qk.scans() });
      qc.invalidateQueries({ queryKey: qk.all });
    },
  });
}

export function useDeleteScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => deleteScan(runId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.scans() });
      qc.invalidateQueries({ queryKey: qk.curationStats() });
    },
  });
}
