export type FileStatus = "uploading" | "complete" | "error";

export interface FileMetadata {
  key: string;
  filename: string;
  folder: string;
  size_bytes: number;
  size_human: string;
  content_type: string;
  uploaded_at: string;
  url: string | null;
}

export interface FileMetadataDetail {
  filename: string;
  size_bytes: number;
  size_human: string;
  mime_type: string;
  extension: string;
  md5: string;
  sha256: string;
  uploaded_at: string;
  // Image-specific
  image_width: number | null;
  image_height: number | null;
  exif: Record<string, string> | null;
  // PDF-specific
  pdf_pages: number | null;
  pdf_author: string | null;
  pdf_title: string | null;
  // Audio/Video
  duration_seconds: number | null;
  codec: string | null;
  bitrate: number | null;
}

export interface FileUploadResponse {
  key: string;
  filename: string;
  size_bytes: number;
  size_human: string;
  content_type: string;
  uploaded_at: string;
  url: string | null;
  metadata: FileMetadataDetail | null;
}

export interface DailyUploadCount {
  date: string;
  uploads: number;
}

export interface UploadStats {
  total_files: number;
  total_size_bytes: number;
  total_size_human: string;
  uploads_today: number;
  total_downloads: number;
}

// --- Curation (fastdup dataset cleaning) ---

export type IssueType = "duplicate" | "near_duplicate" | "outlier" | "broken";
export type Sensitivity = "strict" | "balanced" | "loose";
export type RunStatus = "running" | "complete" | "failed";

export interface DatasetSummary {
  name: string;
  image_count: number;
  size_bytes: number;
  size_human: string;
}

export interface DatasetImage {
  key: string;
  filename: string;
  url: string | null;
  quarantined: boolean;
}

export interface DatasetDetail {
  name: string;
  image_count: number;
  quarantined_count: number;
  images: DatasetImage[];
}

export interface ScanRequest {
  dataset: string;
  sensitivity: Sensitivity;
  issue_types: IssueType[];
  label?: string | null;
}

export interface ScanSummary {
  run_id: string;
  dataset: string;
  label: string | null;
  sensitivity: string;
  issue_types: string[];
  status: RunStatus;
  created_at: string;
  completed_at: string | null;
  total_images: number;
  issues_found: number;
  issues_by_type: Record<string, number>;
  cleaned: boolean;
  quarantined_count: number;
  error: string | null;
}

export interface DuplicateGroup {
  group_id: number;
  keep: string;
  flagged: string[];
  filenames: string[];
  score: number | null;
}

export interface OutlierItem {
  key: string;
  filename: string;
  score: number | null;
}

export interface BrokenItem {
  key: string;
  filename: string;
  reason: string;
}

export interface ScanReport extends ScanSummary {
  duplicates: DuplicateGroup[];
  near_duplicates: DuplicateGroup[];
  outliers: OutlierItem[];
  broken: BrokenItem[];
  preview_urls: Record<string, string>;
}

export interface CleanResult {
  run_id: string;
  quarantined_count: number;
  manifest_key: string;
  already_cleaned: boolean;
}

export interface IssueTypeCount {
  issue_type: string;
  count: number;
}

export interface CurationStats {
  datasets: number;
  images: number;
  issues_found: number;
  quarantined: number;
}
