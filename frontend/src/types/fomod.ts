export interface FomodFileMapping {
  source: string;
  destination: string;
  priority: number;
  is_folder: boolean;
}

export interface FomodFlagSetter {
  name: string;
  value: string;
}

export type PluginTypeString =
  | "Required"
  | "Recommended"
  | "Optional"
  | "NotUsable"
  | "CouldBeUsable";

export interface FomodFlagCondition {
  name: string;
  value: string;
}

export interface FomodFileCondition {
  file: string;
  state: "Active" | "Inactive" | "Missing";
}

export interface FomodCompositeDependency {
  operator: "And" | "Or";
  flag_conditions: FomodFlagCondition[];
  file_conditions: FomodFileCondition[];
  nested: FomodCompositeDependency[];
}

export interface FomodTypeDescriptorPattern {
  dependency: FomodCompositeDependency;
  type: PluginTypeString;
}

export interface FomodTypeDescriptor {
  default_type: PluginTypeString;
  patterns: FomodTypeDescriptorPattern[];
}

export interface FomodPluginOut {
  name: string;
  description: string;
  image_path: string;
  files: FomodFileMapping[];
  condition_flags: FomodFlagSetter[];
  type_descriptor: FomodTypeDescriptor;
}

export interface FomodGroupOut {
  name: string;
  type: string;
  plugins: FomodPluginOut[];
}

export interface FomodStepOut {
  name: string;
  groups: FomodGroupOut[];
  visible: FomodCompositeDependency | null;
}

export interface FomodConfigOut {
  module_name: string;
  module_image: string;
  required_install_files: FomodFileMapping[];
  steps: FomodStepOut[];
  has_conditional_installs: boolean;
  total_steps: number;
}

export interface FomodInstallRequest {
  archive_filename: string;
  mod_name: string;
  selections: Record<number, Record<number, number[]>>;
  skip_conflicts?: string[];
}

export interface FomodPreviewFile {
  game_relative_path: string;
  source: string;
  priority: number;
}

export interface FomodPreviewRequest {
  archive_filename: string;
  selections: Record<number, Record<number, number[]>>;
}

export interface FomodPreviewResult {
  files: FomodPreviewFile[];
  total_files: number;
}
