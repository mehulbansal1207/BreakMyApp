export interface RepoInfo {
  languages: string[];
  has_python: boolean;
  has_javascript: boolean;
  has_typescript: boolean;
  has_dockerfile: boolean;
  has_ci: boolean;
  has_tests: boolean;
  has_requirements: boolean;
  has_package_json: boolean;
  total_files: number;
  repo_size_mb: number;
}

export interface SecretsFinding {
  severity: "CRITICAL";
  type: string;
  detector: string;
  file: string;
  line: number;
  raw: string;
}

export interface SecretsResult {
  tool: "trufflehog";
  status: string;
  findings_count: number;
  findings: SecretsFinding[];
  error: string | null;
}

export interface SemgrepFinding {
  severity: "HIGH" | "MEDIUM" | "LOW";
  rule_id: string;
  message: string;
  file: string;
  line_start: number;
  line_end: number;
  category: string;
  cwe: string[];
}

export interface SemgrepResult {
  tool: "semgrep";
  status: string;
  findings_count: number;
  findings: SemgrepFinding[];
  error: string | null;
}

export interface BanditFinding {
  severity: "HIGH" | "MEDIUM" | "LOW";
  confidence: "HIGH" | "MEDIUM" | "LOW";
  test_id: string;
  test_name: string;
  message: string;
  file: string;
  line: number;
}

export interface BanditResult {
  tool: "bandit";
  status: string;
  findings_count: number;
  findings: BanditFinding[];
  error: string | null;
}

export interface DependencyFinding {
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  package: string;
  installed_version: string;
  fix_version: string;
  vulnerability_id: string;
  description: string;
  ecosystem: "python" | "javascript";
}

export interface DependencyScanSubResult {
  status: string;
  findings_count: number;
  error: string | null;
}

export interface DependenciesResult {
  tool: "dependency_scanner";
  status: string;
  findings_count: number;
  findings: DependencyFinding[];
  python_scan: DependencyScanSubResult;
  javascript_scan: DependencyScanSubResult;
  error: string | null;
}

export interface AiPriority {
  priority: number;
  title: string;
  explanation: string;
  action: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
}

export interface AiCategorySummaries {
  secrets: string;
  security: string;
  dependencies: string;
  code_quality: string;
}

export interface AiExplanation {
  status: "completed" | "failed" | "skipped";
  executive_summary: string;
  score_explanation: string;
  top_priorities: AiPriority[];
  category_summaries: AiCategorySummaries;
  positive_findings: string[];
  error: string | null;
}

export interface Findings {
  repo_info: RepoInfo;
  secrets: SecretsResult;
  semgrep: SemgrepResult;
  bandit: BanditResult;
  dependencies: DependenciesResult;
  ai_explanation: AiExplanation;
}

export interface ScanResponse {
  id: string;
  repo_url: string;
  share_token: string;
  status: "pending" | "running" | "completed" | "failed";
  score: number | null;
  findings: Findings | null;
  created_at: string;
  updated_at: string;
  progress?: number;
  current_step?: string;
}

export interface ScanShareResponse {
  share_token: string;
  repo_url: string;
  status: "pending" | "running" | "completed" | "failed";
  score: number | null;
  top_priorities: AiPriority[];
  executive_summary: string;
  score_explanation: string;
  category_summaries: Partial<AiCategorySummaries>;
  findings_summary: {
    secrets: number;
    security: number;
    code_quality: number;
    dependencies: number;
    custom: number;
  };
  created_at: string;
}

export interface UserResponse {
  id: string;
  email: string;
  firebase_uid: string;
  created_at: string;
  is_active: boolean;
}
