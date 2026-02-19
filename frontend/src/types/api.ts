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
}

export interface ModGroup {
  id: number;
  game_id: number;
  display_name: string;
  confidence: number;
  files: ModFileOut[];
  nexus_match: CorrelationBrief | null;
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
  mod_group_id: number;
  display_name: string;
  local_version: string;
  nexus_version: string;
  nexus_mod_id: number;
  nexus_url: string;
  author: string;
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
  created_at: string;
  mod_count: number;
  mods: ProfileModOut[];
}

export interface ProfileExportMod {
  name: string;
  nexus_mod_id: number | null;
  version: string;
  source_archive: string;
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
