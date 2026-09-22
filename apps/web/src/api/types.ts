export type Role = 'technician' | 'manager' | 'engineer' | 'admin';

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export interface PageParams {
  page?: number;
  size?: number;
  sort?: string;
}

export interface ProblemFieldError {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export interface Problem {
  type?: string;
  title: string;
  status: number;
  detail?: string | null;
  instance?: string | null;
  errors?: ProblemFieldError[];
}

export interface Me {
  id: string;
  sub: string;
  display_name: string;
  email: string | null;
  roles: string[];
  locale: string;
}

export interface Line {
  id: string;
  plant_id: string;
  code: string;
  name: string;
  sequence: number;
  created_at: string;
  updated_at: string;
}

export const ASSET_TYPES = ['cnc_mill', 'compressor', 'conveyor', 'hydraulic_press', 'injection_moulder', 'other'] as const;
export type AssetType = (typeof ASSET_TYPES)[number];

export const ASSET_STATUSES = ['RUNNING', 'IDLE', 'MAINTENANCE', 'DOWN', 'UNKNOWN'] as const;
export type AssetStatus = (typeof ASSET_STATUSES)[number];

export type FidelityLevel = 1 | 2 | 3 | 4;

/** Floor-plan placement in metres; `rot` is the yaw in radians. */
export interface AssetPosition {
  x: number;
  y: number;
  z: number;
  rot: number;
}

export interface Asset {
  id: string;
  line_id: string;
  code: string;
  name: string;
  asset_type: AssetType;
  manufacturer: string | null;
  model: string | null;
  serial_no: string | null;
  install_date: string | null;
  ditto_thing_id: string;
  aas_id: string | null;
  fidelity_level: FidelityLevel;
  ideal_cycle_time_s: number | null;
  rated_power_kw: number | null;
  model_3d_path: string | null;
  position: AssetPosition | null;
  status: AssetStatus;
  attributes: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AssetListParams extends PageParams {
  line_id?: string;
  asset_type?: AssetType;
  status?: AssetStatus;
  q?: string;
}

export interface AssetCreate {
  line_id: string;
  code: string;
  name: string;
  asset_type: AssetType;
  manufacturer?: string | null;
  model?: string | null;
  serial_no?: string | null;
  install_date?: string | null;
  fidelity_level?: FidelityLevel;
  ideal_cycle_time_s?: number | null;
  rated_power_kw?: number | null;
}

export interface AssetClone {
  code: string;
  name: string;
}

export interface Component {
  id: string;
  asset_id: string;
  code: string;
  name: string;
  component_type: string;
  health_weight: number;
  physics_model: string | null;
  physics_params: Record<string, unknown>;
}

export interface Sensor {
  id: string;
  asset_id: string;
  component_id: string | null;
  code: string;
  metric_name: string;
  name: string;
  unit: string;
  kind: string;
  sample_rate_hz: number | null;
  min_valid: number | null;
  max_valid: number | null;
  warn_low: number | null;
  warn_high: number | null;
  alarm_low: number | null;
  alarm_high: number | null;
}

export interface FailureMode {
  id: string;
  asset_type: AssetType;
  code: string;
  name: string;
  component_type: string | null;
  description: string | null;
  signature: { metrics: string[]; pattern: string };
  severity: 1 | 2 | 3 | 4;
}

export interface AasElement {
  modelType: string;
  idShort?: string;
  valueType?: string;
  value?: unknown;
  [key: string]: unknown;
}

export interface AasSubmodel {
  idShort: string;
  id: string;
  semanticId?: unknown;
  submodelElements?: AasElement[];
}

export interface AasEnvironment {
  assetAdministrationShells: unknown[];
  submodels: AasSubmodel[];
  conceptDescriptions: unknown[];
}

export const SUBMODEL_IDS = [
  'Nameplate',
  'TechnicalData',
  'OperationalData',
  'MaintenanceHistory',
  'PredictiveMaintenance',
] as const;
export type SubmodelId = (typeof SUBMODEL_IDS)[number];

export interface Rul {
  point: number;
  low: number;
  high: number;
  unit: string;
}

export interface TreeComponent {
  id: string;
  code: string;
  name: string;
  component_type: string;
  health: number | null;
  rul: Rul | null;
}

export interface TreeAsset {
  id: string;
  code: string;
  name: string;
  asset_type: AssetType;
  status: AssetStatus;
  fidelity_level: FidelityLevel;
  health: number | null;
  /** Optional: servers before the 3D layout (FR-DT-07) do not send these. */
  position?: AssetPosition | null;
  model_3d_path?: string | null;
  components: TreeComponent[];
}

export interface TreeLine {
  id: string;
  code: string;
  name: string;
  health: number | null;
  assets: TreeAsset[];
}

export interface TreePlant {
  id: string;
  code: string;
  name: string;
  health: number | null;
  lines: TreeLine[];
}

export interface TwinTree {
  plants: TreePlant[];
}

export interface TelemetryValue {
  v: number | string | boolean | null;
  u: string | null;
  t: string;
}

export interface Twin {
  code: string;
  asset_id: string;
  thing_id: string;
  policy_id: string;
  revision: number;
  status: AssetStatus;
  fidelity_level: FidelityLevel;
  health: number | null;
  attributes: Record<string, unknown>;
  features: {
    telemetry?: { properties: Record<string, TelemetryValue> };
    state?: { properties: { status: AssetStatus } };
    prediction?: { properties: Record<string, unknown> };
    components?: { properties: Record<string, { health: number | null; rul: Rul | null }> };
  };
}

export type TwinCommand =
  | { command: 'set_load'; params: { load_pct: number } }
  | { command: 'set_speed'; params: { speed_pct: number } }
  | { command: 'maintenance_reset'; params: { component_code?: string | null } };

export type TwinCommandName = TwinCommand['command'];

export type TwinCommandRequest = TwinCommand & { pin: string };

export interface TwinCommandResult {
  command_id: string;
  command: TwinCommandName;
  status: 'accepted' | 'rejected';
  error: string | null;
}

export interface Scenario {
  code: string;
  name: string;
  description: string | null;
}

export type FaultMode = 'gradual' | 'sudden';

export const SENSOR_FAULTS = ['sensor_stuck', 'sensor_offset', 'sensor_dropout', 'sensor_drift'] as const;
export type SensorFault = (typeof SENSOR_FAULTS)[number];

export interface SimAsset {
  code: string;
  asset_type: AssetType;
  line_code: string;
  state: string;
  load_pct: number;
  speed_pct: number;
  damage: Record<string, number>;
  active_modes: { failure_mode: string; mode: FaultMode; severity: number; started_at: string }[];
  sensor_faults: { metric: string; kind: string; until: string | null }[];
  true_rul_h: number | null;
  driver: string | null;
  failure_mode: string;
}

export type LogLevel = 'info' | 'warning' | 'error';

export interface SimLogEntry {
  t: string;
  level: LogLevel;
  message: string;
  asset_code: string | null;
}

export interface SimStatus {
  sim_time: string;
  sim_elapsed_s: number;
  time_scale: number;
  running: boolean;
  seed: number | null;
  scenario: { code: string; started_at: string } | null;
  assets: SimAsset[];
  log: SimLogEntry[];
}

export interface ScenarioStarted {
  scenario_code: string;
  started_at: string;
  seed: number | null;
  time_scale: number;
}

export interface FaultRequest {
  asset: string;
  failure_mode: string;
  mode: FaultMode;
  severity: number;
  metric?: string | null;
  duration_s?: number | null;
}

export interface FaultAccepted {
  accepted: boolean;
  asset: string;
  failure_mode: string;
}

export interface ResetResult {
  asset: string;
  reset_components: string[];
}

export interface ExportRequest {
  scenario_code?: string | null;
  hours: number;
  sample_period_s: number;
  seed?: number | null;
}

export interface ExportResult {
  path: string;
  rows: number;
  columns: string[];
}

// ── M3: Telemetry & Alarms ───────────────────────────────────────────

export interface TelemetryPoint {
  time: string;
  value: number;
  quality: number;
}

export interface TelemetryAggPoint {
  bucket: string;
  avg: number | null;
  min: number | null;
  max: number | null;
  std: number | null;
  n: number;
}

export interface TelemetrySeries {
  sensor_id: string;
  metric_name: string;
  unit: string;
  points: (TelemetryPoint | TelemetryAggPoint)[];
}

export interface TelemetryLatestValue {
  sensor_id: string;
  metric_name: string;
  name: string;
  unit: string;
  value: number | null;
  quality: number;
  time: string | null;
}

export interface TelemetryLatestResponse {
  asset_code: string;
  values: TelemetryLatestValue[];
}

export type AlarmSeverity = 'info' | 'warning' | 'serious' | 'critical';
export type AlarmStatus = 'active' | 'acknowledged' | 'shelved' | 'cleared';
export type AlarmRuleKind = 'threshold' | 'adaptive' | 'ml_anomaly' | 'energy_intensity';

export interface Alarm {
  id: string;
  raised_at: string;
  cleared_at: string | null;
  asset_id: string;
  sensor_id: string | null;
  rule_id: string | null;
  severity: AlarmSeverity;
  title: string;
  message: string;
  value: number | null;
  threshold: number | null;
  prediction_id: string | null;
  status: AlarmStatus;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  assigned_to: string | null;
  shelved_until: string | null;
}

export interface AlarmRule {
  id: string;
  sensor_id: string | null;
  asset_id: string | null;
  kind: AlarmRuleKind;
  params: Record<string, unknown>;
  severity: AlarmSeverity;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

// ── M5: Predictive Maintenance ───────────────────────────────────────

export type ModelStage = 'candidate' | 'production' | 'archived';
export type ModelTask = 'anomaly' | 'failure' | 'rul' | 'survival';

export interface PdmModel {
  id: string;
  name: string;
  version: string;
  task: ModelTask;
  algorithm: string;
  asset_type: string | null;
  asset_id: string | null;
  dataset_ref: string;
  feature_set: string[] | Record<string, unknown>;
  hyperparams: Record<string, unknown>;
  window_size: number | null;
  stride: number | null;
  horizon: number | null;
  artifact_uri: string;
  onnx_uri: string | null;
  stage: ModelStage;
  trained_at: string;
  created_at: string;
  updated_at: string;
}

export interface ModelMetric {
  id: string;
  model_id: string;
  split: string;
  metric: string;
  value: number;
  extra: Record<string, unknown> | null;
}

export interface PredictionRul {
  point: number | null;
  low: number | null;
  high: number | null;
  unit: string;
  coverage: number | null;
}

export interface PredictionConfidence {
  label: 'high' | 'medium' | 'low' | null;
  reasons: string[];
}

export interface PredictionDrift {
  flag: boolean;
  score: number | null;
}

export interface Prediction {
  id: string;
  time: string;
  asset_id: string;
  component_id: string | null;
  model_id: string;
  health_index: number | null;
  anomaly_score: number | null;
  failure_probability: Record<string, number> | null;
  failure_probability_calibrated: Record<string, number> | null;
  rul: PredictionRul;
  confidence: PredictionConfidence;
  drift: PredictionDrift;
  source: string;
  latency_ms: number | null;
}

export interface PredictionLatest {
  asset_code: string;
  prediction: Prediction | null;
}

export interface TrainJob {
  job_id: string;
  status: string;
  model_id: string | null;
  /** The worker's exception message once the job has failed. */
  error?: string | null;
}

// ── Benchmarks (FR-PM-09) ────────────────────────────────────────────

export const BENCHMARK_DATASETS = ['FD001', 'FD002', 'FD003', 'FD004', 'AI4I', 'METROPT3'] as const;
export type BenchmarkDataset = (typeof BENCHMARK_DATASETS)[number];
export type BenchmarkStatus = 'running' | 'done' | 'failed';

/** A PRD §4.5 target: `le` passes when the result is at most `value`, `ge` when at least. */
export interface BenchmarkTarget {
  op: 'le' | 'ge';
  value: number;
}

export interface BenchmarkRun {
  id: string;
  started_at: string;
  finished_at: string | null;
  git_sha: string | null;
  seed: number;
  datasets: string[];
  results: Record<string, Record<string, number>> | null;
  report_uri: string | null;
  status: BenchmarkStatus;
  error: string | null;
  targets: Record<string, Record<string, BenchmarkTarget>>;
}

export interface BenchmarkRunRequest {
  datasets: BenchmarkDataset[];
  seed?: number;
  quick?: boolean;
}

// ── Live twin store (WebSocket updates) ──────────────────────────────

export interface LiveMetric {
  v: number;
  u: string;
}

export interface LiveAsset {
  code: string;
  status?: AssetStatus;
  health?: number | null;
  rul_point?: number | null;
  rul_low?: number | null;
  rul_high?: number | null;
  confidence?: string | null;
  metrics: Record<string, LiveMetric>;
  alarm_count?: number;
  last_update: number; // epoch ms
}


// ── M6: Explainable AI ───────────────────────────────────────────────

export type NarrationKind = 'status' | 'why' | 'confidence' | 'counterfactual' | 'report_summary';
export type FeedbackVerdict = 'agree' | 'disagree' | 'unsure';

export interface Attribution {
  feature: string;
  label: string;
  value: number;
  unit: string;
  contribution: number;
  direction: 'raising' | 'lowering' | 'neutral';
  share: number;
  rank: number;
}

export interface ReasonCardEvidence {
  feature: string;
  label: string;
  value: number;
  unit: string;
  direction: string;
  share: number;
  supports_mode: boolean;
}

export interface ReasonCard {
  symptom: string;
  evidence: ReasonCardEvidence[];
  likely_cause: string;
  action: string;
  confidence: number;
  failure_mode: string;
  parts: string[];
  est_duration_min: number | null;
  kb_entry_id: string | null;
}

export interface Agreement {
  shap_vs_ebm_top3_jaccard: number;
  disagreement: boolean;
  shap_top3: string[];
  ebm_top3: string[];
}

export interface Explanation {
  id: string;
  prediction_id: string;
  created_at: string;
  method: string;
  base_value: number | null;
  attributions: Attribution[];
  temporal_attribution: Record<string, [number, number][]> | null;
  ebm_terms: Record<string, unknown> | null;
  agreement: Agreement | null;
  reason_card: ReasonCard | null;
  compute_ms: number | null;
}

export interface CounterfactualChange {
  feature: string;
  label: string;
  unit: string;
  from: number;
  to: number;
  actionable: boolean;
}

export interface Counterfactual {
  id: string;
  explanation_id: string;
  created_at: string;
  target: string;
  changes: CounterfactualChange[];
  outcome: Record<string, number>;
  feasibility_score: number | null;
  action_text: string | null;
}

export interface NarrationAudit {
  id: string;
  narration_id: string;
  rank_agreement: number;
  sign_agreement: number;
  numeric_within_tolerance: boolean;
  hallucinated_features: string[];
  unsupported_recommendation: boolean;
  passed: boolean;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface Narration {
  id: string;
  explanation_id: string;
  kind: NarrationKind;
  lang: string;
  template_text: string;
  llm_text: string | null;
  llm_model: string | null;
  final_text: string;
  created_at: string;
  audit: NarrationAudit | null;
}

export interface NarrationAuditRow {
  audit: NarrationAudit;
  kind: NarrationKind;
  lang: string;
  final_text: string;
  used_llm: boolean;
}

export interface ExplanationFeedback {
  id: string;
  explanation_id: string;
  user_id: string | null;
  verdict: FeedbackVerdict;
  reason: string | null;
  suspect_sensor_id: string | null;
  channel: string;
  created_at: string;
}

export interface GlobalImportance {
  model_id: string;
  method: string;
  features: { feature: string; importance: number }[];
  partial_dependence: Record<string, [number, number][]>;
}

export interface XaiQualityMetric {
  id: string;
  model_id: string;
  method: string;
  metric: string;
  value: number;
  dataset_ref: string | null;
  computed_at: string;
}

export interface XaiQualityMetrics {
  model_id: string;
  metrics: XaiQualityMetric[];
  narration_audit_pass_rate: number | null;
  narration_audit_count: number;
  /** Audits exist only for LLM paraphrases; without an LLM every narration is the template itself. */
  llm_enabled: boolean;
}

// ── M7: Maintenance ──────────────────────────────────────────────────

export type WorkOrderType = 'corrective' | 'preventive' | 'predictive';
export type WorkOrderStatus = 'open' | 'scheduled' | 'in_progress' | 'closed' | 'cancelled';
export type CreatedVia = 'ui' | 'voice' | 'chat' | 'auto';

export interface Technician {
  id: string;
  user_id: string | null;
  code: string;
  name: string;
  skills: string[];
  hourly_cost: string | null;
  created_at: string;
  updated_at: string;
}

export interface TechnicianAvailability {
  id: string;
  technician_id: string;
  starts_at: string;
  ends_at: string;
  kind: 'available' | 'leave' | 'training';
}

export interface WorkOrderTask {
  id: string;
  work_order_id: string;
  sequence: number;
  description: string;
  done: boolean;
  done_at: string | null;
}

export interface WorkOrder {
  id: string;
  number: number;
  asset_id: string;
  component_id: string | null;
  type: WorkOrderType;
  priority: number;
  title: string;
  description: string | null;
  failure_mode_id: string | null;
  prediction_id: string | null;
  explanation_id: string | null;
  status: WorkOrderStatus;
  planned_start: string | null;
  planned_end: string | null;
  actual_start: string | null;
  actual_end: string | null;
  technician_id: string | null;
  parts: Record<string, unknown>[];
  est_duration_min: number | null;
  est_cost: string | null;
  risk_before_slot: number | null;
  created_via: CreatedVia;
  outcome: string | null;
  prediction_was_correct: boolean | null;
  created_at: string;
  updated_at: string;
}

export interface WorkOrderDetail extends WorkOrder {
  asset_code: string | null;
  technician_name: string | null;
  tasks: WorkOrderTask[];
}

export interface WorkOrderRisk {
  work_order_id: string;
  planned_start: string | null;
  risk: number;
  risk_earlier: number;
  risk_later: number;
  shift_hours: number;
  rul_point: number | null;
  rul_low: number | null;
  rul_high: number | null;
}

export interface ObjectiveWeights {
  downtime_cost: number;
  failure_risk: number;
  energy_cost: number;
}

export interface ScheduleItem {
  id: string;
  schedule_id: string;
  work_order_id: string;
  technician_id: string | null;
  starts_at: string;
  ends_at: string;
  risk_before: number | null;
  energy_cost: string | null;
  manually_adjusted: boolean;
}

export interface ScheduleConflict {
  orders: string[];
  kind: 'technician' | 'line';
}

export interface Schedule {
  id: string;
  created_at: string;
  horizon_start: string;
  horizon_end: string;
  objective: ObjectiveWeights;
  solver_status: string | null;
  solve_ms: number | null;
  objective_value: number | null;
  is_active: boolean;
  items: ScheduleItem[];
  unscheduled: string[];
  conflicts: ScheduleConflict[];
}

// ── M8: Analytics ────────────────────────────────────────────────────

export type AnalyticsScope = 'plant' | 'line' | 'asset';
export type AnalyticsPeriod = 'shift' | 'day' | 'week' | 'month';

export interface KpiDefinition {
  code: string;
  name: string;
  unit: string;
  formula: string;
  standard_ref: string | null;
  version: number;
}

export interface KpiSeries {
  kpi_code: string;
  name: string;
  unit: string;
  formula: string;
  points: { time: string; value: number; inputs: Record<string, unknown> | null }[];
}

export interface OeeResult {
  scope: string;
  scope_id: string;
  period: string;
  from: string;
  to: string;
  oee: number;
  availability: number;
  performance: number;
  quality: number;
  inputs: Record<string, Record<string, unknown>>;
  trend: {
    time: string;
    oee?: number;
    availability?: number;
    performance?: number;
    quality?: number;
  }[];
}

export interface Reliability {
  scope_id: string;
  mtbf_h: number;
  mttr_h: number;
  breakdowns: number;
  repairs: number;
}

export interface DowntimePareto {
  scope: string;
  scope_id: string;
  total_seconds: number;
  rows: { cause_code: string; seconds: number; share: number; cumulative_share: number }[];
}

export interface ProductionPlan {
  scope_id: string;
  planned: number;
  actual: number;
  good: number;
  reject: number;
  attainment: number;
  cycle_time_histogram: { from: number; to: number; count: number }[];
}

export interface EnergySummary {
  scope: string;
  scope_id: string;
  from: string;
  to: string;
  energy_kwh: number;
  cost: number;
  currency: string;
  co2_kg: number;
  peak_demand_kw: number;
  idle_energy_kwh: number;
  idle_energy_share: number;
  energy_per_unit: number | null;
  breakdown: { asset_code: string; asset_name: string; energy_kwh: number }[];
  intensity_trend: {
    time: string;
    units: number;
    energy_kwh: number;
    intensity: number | null;
    expected_kwh: number | null;
  }[];
}

export interface EnergyAnomaly {
  time: string;
  scope_id: string;
  energy_kwh: number;
  expected_kwh: number;
  units: number;
  sigma: number;
  health_index: number | null;
}

export interface EnergyBaseline {
  id: string;
  scope: string;
  scope_id: string;
  period_start: string;
  period_end: string;
  intercept_kwh: number;
  slope_kwh_per_unit: number;
  r2: number | null;
  created_at: string;
}

// ── Voice (M9) ───────────────────────────────────────────────────────

export type VoiceChannel = 'voice' | 'chat';
export type VoiceTier = 'T0' | 'T1' | 'T2' | 'T3';
export type VoiceRouter = 'rules' | 'llm' | 'none';
export type VoiceActionStatus =
  | 'pending'
  | 'confirmed'
  | 'cancelled'
  | 'expired'
  | 'executed'
  | 'failed'
  | 'rejected';

export interface VoiceSession {
  id: string;
  user_id: string | null;
  started_at: string;
  ended_at: string | null;
  channel: string;
  device: string | null;
  lang: string;
  context: Record<string, unknown>;
}

export interface VoiceTurn {
  id: string;
  session_id: string;
  at: string;
  transcript: string | null;
  transcript_confidence: number | null;
  intent: string | null;
  slots: Record<string, unknown> | null;
  intent_confidence: number | null;
  router: string | null;
  router_ms: number | null;
  tier: string | null;
  response_text: string | null;
  citations: Record<string, unknown> | null;
  total_ms: number | null;
}

export interface VoiceSessionDetail extends VoiceSession {
  turns: VoiceTurn[];
}

export interface VoiceAction {
  id: string;
  turn_id: string;
  tool: string;
  params: Record<string, unknown>;
  tier: VoiceTier;
  readback: string | null;
  status: VoiceActionStatus;
  validation_errors: Record<string, string> | null;
  expires_at: string | null;
  confirmed_at: string | null;
  second_factor_ok: boolean | null;
  executed_at: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
}

export interface VoiceSuggestion {
  label: string;
  value: string;
}

export interface TurnResponse {
  session_id: string;
  turn_id: string;
  intent: string;
  tier: VoiceTier;
  router: VoiceRouter;
  confidence: number;
  lang: string;
  slots: Record<string, unknown>;
  text: string;
  citations: Record<string, unknown>;
  hypothetical: boolean;
  action: VoiceAction | null;
  suggestions: VoiceSuggestion[];
  navigate: { path: string; label: string; period: string | null } | null;
  total_ms: number;
}

export interface IntentHelp {
  intent: string;
  tier: string;
  summary: string;
  examples: Record<string, string>;
}

export interface SuiteAccuracy {
  split: string;
  total: number;
  correct: number;
  accuracy: number;
}

// ── Reports (M10) ────────────────────────────────────────────────────

export type ReportType =
  | 'machine_health'
  | 'weekly_maintenance'
  | 'energy'
  | 'benchmark'
  | 'incident';
export type ReportFormat = 'pdf' | 'docx' | 'md' | 'html';
export type ReportStatus = 'queued' | 'running' | 'done' | 'failed';

export interface Report {
  id: string;
  type: ReportType;
  scope: string | null;
  scope_id: string | null;
  period_start: string | null;
  period_end: string | null;
  format: ReportFormat;
  status: ReportStatus;
  file_uri: string | null;
  summary_text: string | null;
  summary_audit: {
    passed: boolean;
    used_llm: boolean;
    word_count: number;
    unsupported_numbers: number[];
    reason: string | null;
  } | null;
  error: string | null;
  requested_by: string | null;
  requested_via: string;
  schedule_id: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface ReportSchedule {
  id: string;
  type: ReportType;
  scope: string | null;
  scope_id: string | null;
  format: ReportFormat;
  cron: string;
  recipients: string[];
  enabled: boolean;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Plant {
  id: string;
  code: string;
  name: string;
  timezone: string;
  grid_emission_factor_kg_per_kwh: number;
  currency: string;
  created_at: string;
  updated_at: string;
}
