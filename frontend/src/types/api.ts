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
