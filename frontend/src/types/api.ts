export interface ModPath {
  id: number;
  relative_path: string;
  description: string;
  is_default: boolean;
}

export interface Game {
  id: number;
  name: string;
  domain_name: string;
  install_path: string;
  os: string;
  created_at: string;
  updated_at: string;
  mod_paths: ModPath[];
}

export interface GameCreate {
  name: string;
  domain_name: string;
  install_path: string;
  os?: string;
  mod_paths?: { relative_path: string; description: string; is_default: boolean }[];
}

export interface ModFileOut {
  id: number;
  file_path: string;
  filename: string;
  file_hash: string;
  file_size: number;
  source_folder: string;
}

export interface CorrelationBrief {
  nexus_mod_id: number;
  mod_name: string;
  score: number;
  method: string;
  confirmed: boolean;
  author: string;
  summary: string;
  version: string;
  endorsement_count: number;
  category: string;
  picture_url: string;
  nexus_url: string;
  updated_at: string | null;
}

export interface ModGroup {
  id: number;
  game_id: number;
  display_name: string;
  confidence: number;
  files: ModFileOut[];
  nexus_match: CorrelationBrief | null;
  earliest_file_mtime: number | null;
}

export interface ScanResult {
  files_found: number;
  groups_created: number;
  new_files: number;
}

export interface CorrelateResult {
  total_groups: number;
  matched: number;
  unmatched: number;
}

export interface NexusKeyResult {
  valid: boolean;
  username: string;
  is_premium: boolean;
  error: string;
}

export type SSOStatus = "pending" | "success" | "error" | "expired";

export interface SSOStartResult {
  uuid: string;
  authorize_url: string;
}

export interface SSOPollResult {
  status: SSOStatus;
  result: NexusKeyResult | null;
  error: string;
}

export interface NexusSyncResult {
  tracked_mods: number;
  endorsed_mods: number;
  total_stored: number;
}

export interface NexusDownload {
  id: number;
  nexus_mod_id: number;
  mod_name: string;
  file_name: string;
  version: string;
  category: string;
  downloaded_at: string | null;
  nexus_url: string;
  is_tracked: boolean;
  is_endorsed: boolean;
  author: string;
  summary: string;
  endorsement_count: number;
  picture_url: string;
  updated_at: string | null;
}

export interface NexusDownloadBrief {
  nexus_mod_id: number;
  mod_name: string;
  version: string;
  nexus_url: string;
}

export interface Setting {
  key: string;
  value: string;
}

export interface PCSpecs {
  cpu: string;
  gpu: string;
  ram_gb: number;
  vram_gb: number;
  storage_type: string;
  os_version: string;
  resolution: string;
}

export interface OnboardingStatus {
  completed: boolean;
  current_step: number;
  has_openai_key: boolean;
  has_nexus_key: boolean;
  has_game: boolean;
}

export interface ModUpdate {
  mod_group_id: number | null;
  display_name: string;
  local_version: string;
  nexus_version: string;
  nexus_mod_id: number;
  nexus_file_id: number | null;
  nexus_file_name: string;
  nexus_url: string;
  author: string;
  installed_mod_id: number | null;
  source: string;
  local_timestamp: number | null;
  nexus_timestamp: number | null;
  source_archive: string | null;
  reason: string;
  local_download_date: number | null;
}

export interface GameVersion {
  version: string | null;
  exe_path: string;
}

export interface DetectedGame {
  path: string;
  source: string;
}

export interface PathValidation {
  valid: boolean;
  path: string;
  found_exe: boolean;
  found_mod_dirs: string[];
  warning: string;
}

export interface UpdateCheckResult {
  total_checked: number;
  updates_available: number;
  updates: ModUpdate[];
}

export interface ChatMessage {
  id: number;
  role: string;
  content: string;
  tool_calls_json: string;
  created_at: string;
}

// Install feature types

export interface AvailableArchive {
  filename: string;
  size: number;
  nexus_mod_id: number | null;
  parsed_name: string;
  parsed_version: string | null;
  is_installed: boolean;
  installed_mod_id: number | null;
  last_downloaded_at: string | null;
}

export interface ArchiveDeleteResult {
  filename: string;
  deleted: boolean;
  message: string;
}

export interface OrphanCleanupResult {
  deleted_count: number;
  freed_bytes: number;
  deleted_files: string[];
}

export interface InstalledModOut {
  id: number;
  name: string;
  source_archive: string;
  nexus_mod_id: number | null;
  installed_version: string;
  disabled: boolean;
  installed_at: string;
  file_count: number;
  mod_group_id: number | null;
  nexus_updated_at: string | null;
  nexus_name: string | null;
  summary: string | null;
  author: string | null;
  endorsement_count: number | null;
  picture_url: string | null;
  category: string | null;
  last_downloaded_at: string | null;
  nexus_url: string | null;
  is_tracked: boolean;
  is_endorsed: boolean;
}

export interface InstallRequest {
  archive_filename: string;
  skip_conflicts: string[];
}

export interface InstallResult {
  installed_mod_id: number;
  name: string;
  files_extracted: number;
  files_skipped: number;
  files_overwritten: number;
}

export interface UninstallResult {
  files_deleted: number;
  directories_removed: number;
}

export interface ToggleResult {
  disabled: boolean;
  files_affected: number;
}

export interface FileConflict {
  file_path: string;
  owning_mod_id: number;
  owning_mod_name: string;
}

export interface ConflictCheckResult {
  archive_filename: string;
  total_files: number;
  conflicts: FileConflict[];
  is_fomod: boolean;
}

export interface ArchiveEntryNode {
  name: string;
  is_dir: boolean;
  size: number;
  children: ArchiveEntryNode[];
}

export interface ArchiveContentsResult {
  filename: string;
  total_files: number;
  total_size: number;
  tree: ArchiveEntryNode[];
}

// Conflicts inbox types

export type ConflictSeverity = "critical" | "warning" | "info";

export interface ConflictEvidence {
  file_path: string;
  winner_mod_id: number;
  winner_mod_name: string;
}

export interface ModConflictSummary {
  mod_id: number;
  mod_name: string;
  source_archive: string;
  total_archive_files: number;
  conflict_count: number;
  severity: ConflictSeverity;
  conflicting_mod_names: string[];
}

export interface ModConflictDetail {
  mod_id: number;
  mod_name: string;
  source_archive: string;
  total_archive_files: number;
  evidence: ConflictEvidence[];
}

export interface ConflictsOverview {
  total_conflicts: number;
  mods_affected: number;
  summaries: ModConflictSummary[];
}

export interface ResolveResult {
  installed_mod_id: number;
  files_extracted: number;
  files_reclaimed: number;
}

// Profile feature types

export interface ProfileModOut {
  installed_mod_id: number;
  name: string;
  enabled: boolean;
}

export interface ProfileOut {
  id: number;
  name: string;
  game_id: number;
  description: string;
  created_at: string;
  last_loaded_at: string | null;
  is_active: boolean;
  is_drifted: boolean;
  mod_count: number;
  mods: ProfileModOut[];
}

export interface ProfileUpdate {
  name?: string;
  description?: string;
}

export interface ProfileDiffEntry {
  mod_name: string;
  installed_mod_id: number | null;
  action: "enable" | "disable" | "missing" | "unchanged";
}

export interface ProfileDiffOut {
  profile_name: string;
  entries: ProfileDiffEntry[];
  enable_count: number;
  disable_count: number;
  missing_count: number;
  unchanged_count: number;
}

export interface SkippedMod {
  name: string;
  installed_mod_id: number | null;
}

export interface ProfileLoadResult {
  profile: ProfileOut;
  skipped_mods: SkippedMod[];
  skipped_count: number;
}

export interface ProfileImportResult {
  profile: ProfileOut;
  matched_count: number;
  skipped_mods: SkippedMod[];
  skipped_count: number;
}

export interface ProfileDuplicateRequest {
  name: string;
}

export interface ProfileCompareEntry {
  mod_name: string;
  installed_mod_id: number | null;
  enabled_in_a: boolean | null;
  enabled_in_b: boolean | null;
}

export interface ProfileCompareOut {
  profile_a_name: string;
  profile_b_name: string;
  only_in_a: ProfileCompareEntry[];
  only_in_b: ProfileCompareEntry[];
  in_both: ProfileCompareEntry[];
  only_in_a_count: number;
  only_in_b_count: number;
  in_both_count: number;
}

export interface ProfileCompareRequest {
  profile_id_a: number;
  profile_id_b: number;
}

export interface ProfileExportMod {
  name: string;
  nexus_mod_id: number | null;
  version: string;
  source_archive: string;
  enabled: boolean;
}

export interface ProfileExport {
  type: string;
  version: string;
  profile_name: string;
  game_name: string;
  exported_at: string;
  mod_count: number;
  mods: ProfileExportMod[];
}

// Download feature types

export interface DownloadRequest {
  nexus_mod_id: number;
  nexus_file_id: number;
  nxm_key?: string;
  nxm_expires?: number;
}

export type DownloadStatus =
  | "pending"
  | "downloading"
  | "completed"
  | "failed"
  | "cancelled";

export interface DownloadJobOut {
  id: number;
  nexus_mod_id: number;
  nexus_file_id: number;
  file_name: string;
  status: DownloadStatus;
  progress_bytes: number;
  total_bytes: number;
  percent: number;
  error: string;
  created_at: string;
  completed_at: string | null;
}

export interface DownloadStartResult {
  job: DownloadJobOut | null;
  requires_nxm: boolean;
  requires_file_selection: boolean;
}

// Trending feature types

export interface TrendingMod {
  mod_id: number;
  name: string;
  summary: string;
  author: string;
  version: string;
  picture_url: string;
  endorsement_count: number;
  mod_downloads: number;
  mod_unique_downloads: number;
  created_timestamp: number;
  updated_timestamp: number;
  category_id: number | null;
  nexus_url: string;
  is_installed: boolean;
  is_tracked: boolean;
  is_endorsed: boolean;
}

export interface NexusModFileDetail {
  file_id: number;
  file_name: string;
  version: string;
  category_id: number | null;
  uploaded_timestamp: number | null;
  file_size: number;
}

export interface ModActionResult {
  success: boolean;
  is_endorsed?: boolean;
  is_tracked?: boolean;
}

export interface ModDetail {
  nexus_mod_id: number;
  game_domain: string;
  name: string;
  summary: string;
  description: string;
  author: string;
  version: string;
  created_at: string | null;
  updated_at: string | null;
  endorsement_count: number;
  mod_downloads: number;
  category: string;
  picture_url: string;
  nexus_url: string;
  changelogs: Record<string, string[]>;
  files: NexusModFileDetail[];
  is_tracked: boolean;
  is_endorsed: boolean;
}

export interface TrendingResult {
  trending: TrendingMod[];
  latest_updated: TrendingMod[];
  cached: boolean;
}
