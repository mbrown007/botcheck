import type { components, paths } from "./generated";

type ApiSchema = components["schemas"];

// ---------------------------------------------------------------------------
// Scenario types
// ---------------------------------------------------------------------------

type ApiScenarioSummary = ApiSchema["ScenarioResponse"];

export type ScenarioSummary = ApiScenarioSummary & {
  scenario_kind: "graph" | "ai";
};

export type ScenarioType = ApiSchema["ScenarioType"];

export type ScenarioPersona = ApiSchema["PersonaConfig"];

export type BotProtocol = ApiSchema["BotProtocol"];

export type ScenarioBotConfig = ApiSchema["BotConfig"];

export type AdversarialTechnique = ApiSchema["AdversarialTechnique"];

export type ScenarioTurnExpectation = ApiSchema["TurnExpectation"];

export type ScenarioTurnConfig = Partial<ApiSchema["TurnConfig"]>;

export type ScenarioBranchMode = "classifier" | "keyword" | "regex";

export interface ScenarioBranchCase {
  condition: string;
  next: string;
  match?: string | null;
  regex?: string | null;
}

export interface ScenarioBranchConfig {
  cases: ScenarioBranchCase[];
  default: string;
  mode?: ScenarioBranchMode;
}

type ApiScenarioTurn =
  | ApiSchema["HarnessPromptBlock"]
  | ApiSchema["BotListenBlock"]
  | ApiSchema["HangupBlock"]
  | ApiSchema["WaitBlock"]
  | ApiSchema["TimeRouteBlock"];

export type ScenarioPromptContent = ApiSchema["PromptContent"];

export type ScenarioTurn = ApiScenarioTurn & Record<string, unknown>;

export interface ScenarioValidationError {
  field: string;
  message: string;
}

export type ScenarioValidationWarning = {
  code: "CYCLE_GUARANTEED_LOOP" | "CYCLE_UNLIMITED_VISIT";
  message: string;
  turn_ids: string[];
};

type ApiScenarioValidationResult =
  paths["/scenarios/validate"]["post"]["responses"][200]["content"]["application/json"];

export type ScenarioValidationResult = Omit<ApiScenarioValidationResult, "errors" | "warnings"> &
  Partial<Pick<ApiScenarioValidationResult, "warnings">> & {
    errors: ScenarioValidationError[];
    warnings?: ScenarioValidationWarning[];
  };

export type ScenarioSourceResponse = ApiSchema["ScenarioSourceResponse"];

export type ScenarioCacheRebuildResponse = ApiSchema["ScenarioCacheRebuildResponse"];

export interface GeneratedScenario {
  yaml: string;
  name: string;
  type: string;
  technique: string;
  turns: number;
}

type ApiGenerateJobResponse =
  paths["/scenarios/generate/{job_id}"]["get"]["responses"][200]["content"]["application/json"];

export type GenerateJobResponse = Omit<ApiGenerateJobResponse, "errors" | "scenarios"> & {
  errors: string[];
  scenarios: GeneratedScenario[];
};

export type ScenarioCacheTurnState = ApiSchema["ScenarioCacheTurnState"];

export type ScenarioCacheStateResponse = ApiSchema["ScenarioCacheStateResponse"] & {
  bucket_name?: string | null;
};

export interface AIPersonaSummary {
  persona_id: string;
  name: string;
  display_name: string;
  avatar_url?: string | null;
  backstory_summary?: string | null;
  style?: string | null;
  voice?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AIPersonaDetail extends AIPersonaSummary {
  system_prompt: string;
}

export interface AIPersonaUpsertRequest {
  name: string;
  display_name?: string | null;
  avatar_url?: string | null;
  backstory_summary?: string | null;
  system_prompt: string;
  style?: string | null;
  voice?: string | null;
  is_active?: boolean;
}

export interface AIScenarioSummary {
  ai_scenario_id: string;
  scenario_id: string;
  name: string;
  namespace?: string | null;
  persona_id: string;
  scenario_brief: string;
  scenario_facts: Record<string, unknown>;
  evaluation_objective: string;
  opening_strategy: "wait_for_bot_greeting" | "caller_opens";
  is_active: boolean;
  scoring_profile?: string | null;
  dataset_source?: string | null;
  record_count: number;
  created_at: string;
  updated_at: string;
}

export interface AIScenarioDetail extends AIScenarioSummary {
  config: Record<string, unknown>;
}

export interface AIScenarioUpsertRequest {
  ai_scenario_id?: string | null;
  scenario_id: string;
  persona_id: string;
  name?: string | null;
  namespace?: string | null;
  scenario_brief?: string | null;
  scenario_facts?: Record<string, unknown>;
  evaluation_objective?: string | null;
  opening_strategy?: "wait_for_bot_greeting" | "caller_opens";
  is_active?: boolean;
  scoring_profile?: string | null;
  dataset_source?: string | null;
  config?: Record<string, unknown>;
}

export interface AIScenarioRecord {
  record_id: string;
  ai_scenario_id: string;
  order_index: number;
  input_text: string;
  expected_output: string;
  metadata: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AIScenarioRecordUpsertRequest {
  order_index?: number | null;
  input_text: string;
  expected_output: string;
  metadata?: Record<string, unknown>;
  is_active?: boolean;
}

export type ScenarioRubricEntry = ApiSchema["DimensionRubric"];

export type ScenarioScoring = ApiSchema["ScenarioScoring"];

export type ScenarioConfig = ApiSchema["ScenarioConfig"];

type ApiScenarioDefinition = ApiSchema["ScenarioDefinition"];

// For existing UI usage, treat nested objects as present even if omitted in raw payload.
export type ScenarioDefinition = Omit<
  ApiScenarioDefinition,
  "config" | "persona" | "scoring" | "tags" | "turns"
> & {
  config: NonNullable<ApiScenarioDefinition["config"]>;
  persona: NonNullable<ApiScenarioDefinition["persona"]>;
  scoring: NonNullable<ApiScenarioDefinition["scoring"]>;
  tags: NonNullable<ApiScenarioDefinition["tags"]>;
  turns: ScenarioTurn[];
};

// ---------------------------------------------------------------------------
// Run types
// ---------------------------------------------------------------------------

export interface RunEvent {
  ts?: string;
  type: string;
  detail?: Record<string, unknown>;
}

export type ScoringDimension = ApiSchema["ScoringDimension"];

export type MetricType = ApiSchema["RunScore"]["metric_type"];

export interface RunFinding {
  dimension: string;
  turn_id: string;
  turn_number: number;
  visit?: number | null;
  speaker: string;
  quoted_text: string;
  finding: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  positive: boolean;
}

export interface ConversationTurn {
  turn_id: string;
  turn_number?: number;
  speaker: "harness" | "bot";
  text: string;
  audio_start_ms?: number;
  audio_end_ms?: number;
  started_at?: string;
  completed_at?: string;
}

type ApiRunScore = ApiSchema["RunScore"];

export type RunScore = Omit<ApiRunScore, "findings" | "reasoning"> & {
  findings?: RunFinding[];
  reasoning?: string;
};

type ApiRunResponse = ApiSchema["RunResponse"];

export type RunResponse = Omit<
  ApiRunResponse,
  "scores" | "findings" | "events" | "conversation" | "failed_dimensions"
> & {
  failed_dimensions: string[];
  scores: Record<string, RunScore>;
  findings: RunFinding[];
  events?: RunEvent[];
  conversation: ConversationTurn[];
  transport_profile_id_at_start?: string | null;
  dial_target_at_start?: string | null;
};

export type PlaygroundMode = ApiSchema["PlaygroundMode"];

export type PlaygroundPresetSummary = ApiSchema["PlaygroundPresetSummary"];

export type PlaygroundPresetDetail = ApiSchema["PlaygroundPresetDetail"];

export type PlaygroundPresetWrite = ApiSchema["PlaygroundPresetWrite"];

export type PlaygroundPresetPatch = ApiSchema["PlaygroundPresetPatch"];

type ApiGateResponse = ApiSchema["GateResponse"];

export type GateResponse = Omit<ApiGateResponse, "failed_dimensions"> & {
  failed_dimensions: string[];
};

export interface RunOperatorActionResponse {
  run_id: string;
  applied: boolean;
  state: string;
  reason: string;
}

// ---------------------------------------------------------------------------
// Tenant / Features types
// ---------------------------------------------------------------------------

export type TenantInfo = ApiSchema["TenantResponse"];
export type CurrentUserResponse = ApiSchema["CurrentUserResponse"];

export interface ProviderCircuitState {
  source: "api" | "agent" | "judge";
  provider: string;
  service: string;
  component: string;
  state: "open" | "half_open" | "closed" | "unknown";
  updated_at?: string | null;
}

export type SpeechProviderCapability = ApiSchema["SpeechProviderCapability"];

export type SpeechCapabilities = ApiSchema["SpeechCapabilities"];

export interface FeaturesResponse {
  tts_cache_enabled: boolean;
  packs_enabled?: boolean;
  destinations_enabled?: boolean;
  ai_scenarios_enabled?: boolean;
  speech_capabilities?: SpeechCapabilities;
  provider_degraded?: boolean;
  harness_degraded?: boolean;
  harness_state?: "open" | "half_open" | "closed" | "unknown";
  provider_circuits?: ProviderCircuitState[];
}

export interface ProviderAvailabilitySummaryResponse {
  provider_id: string;
  vendor: string;
  model: string;
  capability: string;
  runtime_scopes: string[];
  credential_source: string;
  configured: boolean;
  availability_status: string;
  supports_tenant_credentials: boolean;
}

export interface ProviderAvailableListResponse {
  items: ProviderAvailabilitySummaryResponse[];
}

export interface TenantProviderUsageSummaryResponse {
  provider_id: string;
  vendor: string;
  model: string;
  capability: string;
  runtime_scopes: string[];
  last_recorded_at?: string | null;
  input_tokens_24h: number;
  output_tokens_24h: number;
  audio_seconds_24h: number;
  characters_24h: number;
  sip_minutes_24h: number;
  request_count_24h: number;
  calculated_cost_microcents_24h?: number | null;
}

export interface TenantProviderUsageListResponse {
  window_start: string;
  window_end: string;
  items: TenantProviderUsageSummaryResponse[];
}

export interface TenantProviderQuotaMetricResponse {
  metric: string;
  limit_per_day: number;
  used_24h: number;
  remaining_24h: number;
  soft_limit_pct: number;
  percent_used: number;
  status: string;
  soft_limit_reached: boolean;
  hard_limit_reached: boolean;
}

export interface TenantProviderQuotaSummaryResponse {
  provider_id: string;
  vendor: string;
  model: string;
  capability: string;
  metrics: TenantProviderQuotaMetricResponse[];
}

export interface TenantProviderQuotaListResponse {
  window_start: string;
  window_end: string;
  items: TenantProviderQuotaSummaryResponse[];
}

// ---------------------------------------------------------------------------
// Destination types
// ---------------------------------------------------------------------------

export type DestinationProtocol = "sip" | "http" | "webrtc" | "mock";

export interface DirectHTTPTransportConfig {
  http_mode?: "generic_json" | "json_sse_chat";
  method?: "POST";
  request_content_type?: "json";
  request_text_field?: string;
  request_history_field?: string | null;
  request_session_id_field?: string | null;
  request_body_defaults?: Record<string, unknown>;
  response_text_field?: string;
  timeout_s?: number;
  max_retries?: number;
}

export interface WebRTCTransportConfig {
  provider?: "livekit";
  session_mode?: "bot_builder_preview";
  api_base_url?: string;
  agent_id?: string;
  version_id?: string;
  auth_headers?: Record<string, unknown>;
  join_timeout_s?: number;
}

export interface BotDestinationSummary {
  destination_id: string;
  transport_profile_id: string;
  name: string;
  protocol: DestinationProtocol;
  endpoint?: string | null;
  default_dial_target?: string | null;
  caller_id?: string | null;
  trunk_id?: string | null;
  trunk_pool_id?: string | null;
  header_count?: number;
  direct_http_config?: DirectHTTPTransportConfig | null;
  webrtc_config?: WebRTCTransportConfig | null;
  is_active: boolean;
  provisioned_channels?: number | null;
  reserved_channels?: number | null;
  botcheck_max_channels?: number | null;
  capacity_scope?: string | null;
  effective_channels?: number | null;
  active_schedule_count?: number;
  active_pack_run_count?: number;
  in_use?: boolean;
  created_at: string;
  updated_at: string;
}

export interface BotDestinationDetail extends BotDestinationSummary {
  headers: Record<string, unknown>;
}

export interface BotDestinationUpsertRequest {
  name: string;
  protocol: DestinationProtocol;
  endpoint?: string | null;
  default_dial_target?: string | null;
  caller_id?: string | null;
  trunk_id?: string | null;
  trunk_pool_id?: string | null;
  headers?: Record<string, unknown>;
  direct_http_config?: DirectHTTPTransportConfig | null;
  webrtc_config?: WebRTCTransportConfig | null;
  is_active?: boolean;
  provisioned_channels?: number | null;
  reserved_channels?: number | null;
  botcheck_max_channels?: number | null;
  capacity_scope?: string | null;
}

// ---------------------------------------------------------------------------
// Grai eval types
// ---------------------------------------------------------------------------

export interface GraiEvalAssertionPayload {
  assertion_type: string;
  raw_value?: string | null;
  threshold?: number | null;
  weight?: number;
}

export interface GraiEvalPromptPayload {
  label: string;
  prompt_text: string;
  metadata_json?: Record<string, unknown>;
}

export interface GraiEvalCasePayload {
  description?: string | null;
  vars_json?: Record<string, unknown>;
  assert_json: GraiEvalAssertionPayload[];
  tags_json?: string[];
  metadata_json?: Record<string, unknown>;
  import_threshold?: number | null;
}

export interface GraiEvalSuiteUpsertRequest {
  name: string;
  description?: string | null;
  prompts: GraiEvalPromptPayload[];
  cases: GraiEvalCasePayload[];
  metadata_json?: Record<string, unknown>;
}

export interface GraiEvalSuiteImportRequest {
  yaml_content: string;
  name?: string | null;
}

export interface GraiEvalSuiteSummary {
  suite_id: string;
  name: string;
  description?: string | null;
  prompt_count: number;
  case_count: number;
  has_source_yaml: boolean;
  created_at: string;
  updated_at: string;
}

export interface GraiEvalPromptResponse {
  prompt_id: string;
  label: string;
  prompt_text: string;
  metadata_json: Record<string, unknown>;
}

export interface GraiEvalAssertionResponse {
  assertion_type: string;
  passed?: boolean | null;
  score?: number | null;
  threshold?: number | null;
  weight: number;
  raw_value?: string | null;
  failure_reason?: string | null;
  latency_ms?: number | null;
}

export interface GraiEvalCaseResponse {
  case_id: string;
  description?: string | null;
  vars_json: Record<string, unknown>;
  assert_json: GraiEvalAssertionResponse[];
  tags_json: string[];
  metadata_json: Record<string, unknown>;
  import_threshold?: number | null;
}

export interface GraiEvalSuiteDetail {
  suite_id: string;
  name: string;
  description?: string | null;
  source_yaml?: string | null;
  metadata_json: Record<string, unknown>;
  prompts: GraiEvalPromptResponse[];
  cases: GraiEvalCaseResponse[];
  created_at: string;
  updated_at: string;
}

export type GraiEvalResultStatusFilter = "passed" | "failed";

export interface GraiEvalResultFilters {
  prompt_id?: string | null;
  assertion_type?: string | null;
  tag?: string | null;
  status?: GraiEvalResultStatusFilter | null;
  destination_index?: number | null;
}

export interface GraiEvalAssertionTypeBreakdown {
  assertion_type: string;
  total_results: number;
  passed_results: number;
  failed_results: number;
}

export interface GraiEvalFailingPromptVariant {
  prompt_id: string;
  prompt_label: string;
  failure_count: number;
  failed_pairs: number;
}

export interface GraiEvalTagFailureCluster {
  tag: string;
  failure_count: number;
  failed_pairs: number;
}

export interface GraiEvalResultListItem {
  eval_result_id: string;
  destination_index?: number | null;
  transport_profile_id?: string | null;
  destination_label?: string | null;
  prompt_id: string;
  prompt_label: string;
  case_id: string;
  case_description?: string | null;
  assertion_index: number;
  assertion_type: string;
  passed: boolean;
  score?: number | null;
  threshold?: number | null;
  weight: number;
  raw_value?: string | null;
  failure_reason?: string | null;
  latency_ms?: number | null;
  tags_json: string[];
  raw_s3_key?: string | null;
  created_at: string;
}

export interface GraiEvalRunDestination {
  destination_index: number;
  transport_profile_id: string;
  label: string;
  protocol: string;
  endpoint_at_start: string;
  headers_at_start: Record<string, unknown>;
  direct_http_config_at_start?: Record<string, unknown> | null;
}

export interface GraiEvalRunCreateRequest {
  suite_id: string;
  transport_profile_id?: string | null;
  transport_profile_ids: string[];
}

export interface GraiEvalRunHistoryDestination {
  destination_index: number;
  transport_profile_id: string;
  label: string;
}

export interface GraiEvalRunHistorySummary {
  eval_run_id: string;
  suite_id: string;
  transport_profile_id: string;
  transport_profile_ids: string[];
  destination_count: number;
  destinations: GraiEvalRunHistoryDestination[];
  status: string;
  terminal_outcome?: string | null;
  trigger_source: string;
  schedule_id?: string | null;
  triggered_by?: string | null;
  prompt_count: number;
  case_count: number;
  total_pairs: number;
  dispatched_count: number;
  completed_count: number;
  failed_count: number;
  created_at: string;
  updated_at: string;
}

export interface GraiEvalRunResponse {
  eval_run_id: string;
  suite_id: string;
  transport_profile_id: string;
  transport_profile_ids: string[];
  endpoint_at_start: string;
  headers_at_start: Record<string, unknown>;
  direct_http_config_at_start?: Record<string, unknown> | null;
  destinations: GraiEvalRunDestination[];
  trigger_source: string;
  schedule_id?: string | null;
  triggered_by?: string | null;
  status: string;
  terminal_outcome?: string | null;
  prompt_count: number;
  case_count: number;
  total_pairs: number;
  dispatched_count: number;
  completed_count: number;
  failed_count: number;
  created_at: string;
  updated_at: string;
}

export interface GraiEvalRunProgressResponse {
  eval_run_id: string;
  status: string;
  terminal_outcome?: string | null;
  prompt_count: number;
  case_count: number;
  total_pairs: number;
  dispatched_count: number;
  completed_count: number;
  failed_count: number;
  progress_fraction: number;
  updated_at: string;
}

export interface GraiEvalRunCancelResponse {
  eval_run_id: string;
  applied: boolean;
  status: string;
  reason: string;
}

export interface GraiEvalResultPageResponse {
  eval_run_id: string;
  filters: GraiEvalResultFilters;
  items: GraiEvalResultListItem[];
  next_cursor?: string | null;
}

export interface GraiEvalReportResponse {
  eval_run_id: string;
  suite_id: string;
  status: string;
  terminal_outcome?: string | null;
  total_pairs: number;
  filters: GraiEvalResultFilters;
  total_results: number;
  passed_results: number;
  failed_results: number;
  assertion_type_breakdown: GraiEvalAssertionTypeBreakdown[];
  failing_prompt_variants: GraiEvalFailingPromptVariant[];
  tag_failure_clusters: GraiEvalTagFailureCluster[];
  exemplar_failures: GraiEvalResultListItem[];
}

export type GraiEvalMatrixCellStatus = "passed" | "failed" | "error" | "pending";

export interface GraiEvalMatrixAssertionResult {
  assertion_index: number;
  assertion_type: string;
  passed: boolean;
  failure_reason?: string | null;
}

export interface GraiEvalMatrixCell {
  destination_index: number;
  transport_profile_id: string;
  destination_label: string;
  status: GraiEvalMatrixCellStatus;
  artifact_eval_result_id?: string | null;
  response_snippet?: string | null;
  latency_ms?: number | null;
  assertion_results: GraiEvalMatrixAssertionResult[];
}

export interface GraiEvalMatrixRow {
  prompt_id: string;
  case_id: string;
  case_description?: string | null;
  tags_json: string[];
  cells: GraiEvalMatrixCell[];
}

export interface GraiEvalMatrixPromptGroup {
  prompt_id: string;
  prompt_label: string;
  prompt_text: string;
  rows: GraiEvalMatrixRow[];
}

export interface GraiEvalMatrixDestinationSummary {
  destination_index: number;
  transport_profile_id: string;
  label: string;
  protocol: string;
  pass_rate: number;
  total_pairs: number;
  passed: number;
  failed: number;
  errors: number;
  avg_latency_ms?: number | null;
}

export interface GraiEvalMatrixResponse {
  eval_run_id: string;
  suite_id: string;
  status: string;
  terminal_outcome?: string | null;
  total_pairs: number;
  destinations: GraiEvalMatrixDestinationSummary[];
  prompt_groups: GraiEvalMatrixPromptGroup[];
}

export interface GraiEvalArtifactResponse {
  prompt_id: string;
  case_id: string;
  prompt_text: string;
  vars_json: Record<string, unknown>;
  response_text: string;
  assertions: Record<string, unknown>[];
}

export interface SIPTrunkSummary {
  trunk_id: string;
  name?: string | null;
  provider_name?: string | null;
  address?: string | null;
  transport?: string | null;
  numbers: string[];
  metadata_json: Record<string, unknown>;
  is_active: boolean;
  last_synced_at: string;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Auth types
// ---------------------------------------------------------------------------

export type AuthLoginRequest = ApiSchema["LoginRequest"];

export type AuthLoginResponse = ApiSchema["LoginResponse"];

export type AuthTotpLoginRequest = ApiSchema["TotpLoginRequest"];

export type TotpStatusResponse = ApiSchema["TotpStatusResponse"];

export type TotpEnrollmentStartResponse = ApiSchema["TotpEnrollmentStartResponse"];

export type TotpEnrollmentConfirmRequest = ApiSchema["TotpEnrollmentConfirmRequest"];

export type TotpEnrollmentConfirmResponse = ApiSchema["TotpEnrollmentConfirmResponse"];

export type TotpRecoveryCodesRegenerateResponse =
  ApiSchema["TotpRecoveryCodesRegenerateResponse"];

export type LogoutAllResponse = ApiSchema["LogoutAllResponse"];

// ---------------------------------------------------------------------------
// Admin types
// ---------------------------------------------------------------------------

export type AdminUsersListResponse = ApiSchema["AdminUsersListResponse"];
export type AdminUserDetailResponse = ApiSchema["AdminUserDetailResponse"];
export type AdminUserSummaryResponse = ApiSchema["AdminUserSummaryResponse"];
export type AdminUserCreateRequest = ApiSchema["AdminUserCreateRequest"];
export type AdminUserPatchRequest = ApiSchema["AdminUserPatchRequest"];
export type AdminUserActionResponse = ApiSchema["AdminUserActionResponse"];
export type AdminUserReset2FAResponse = ApiSchema["AdminUserReset2FAResponse"];
export type AdminUserPasswordResetRequest = ApiSchema["AdminUserPasswordResetRequest"];

export type AdminTenantsListResponse = ApiSchema["AdminTenantsListResponse"];
export type AdminTenantDetailResponse = ApiSchema["AdminTenantDetailResponse"];
export type AdminTenantSummaryResponse = ApiSchema["AdminTenantSummaryResponse"];
export type AdminTenantCreateRequest = ApiSchema["AdminTenantCreateRequest"];
export type AdminTenantPatchRequest = ApiSchema["AdminTenantPatchRequest"];
export type AdminTenantActionResponse = ApiSchema["AdminTenantActionResponse"];

export type AdminAuditEventDetailResponse = ApiSchema["AdminAuditEventDetailResponse"];
export type AdminAuditEventsListResponse = ApiSchema["AdminAuditEventsListResponse"];
export type AdminSIPTrunkDetailResponse = ApiSchema["AdminSIPTrunkDetailResponse"];
export type AdminSIPTrunksListResponse = ApiSchema["AdminSIPTrunksListResponse"];
export type AdminSIPTrunkPoolDetailResponse = ApiSchema["AdminSIPTrunkPoolDetailResponse"];
export type AdminSIPTrunkPoolsListResponse = ApiSchema["AdminSIPTrunkPoolsListResponse"];
export type AdminSIPTrunkPoolCreateRequest = ApiSchema["AdminSIPTrunkPoolCreateRequest"];
export type AdminSIPTrunkPoolPatchRequest = ApiSchema["AdminSIPTrunkPoolPatchRequest"];
export type AdminSIPTrunkPoolMemberCreateRequest =
  ApiSchema["AdminSIPTrunkPoolMemberCreateRequest"];
export interface AdminSIPTrunkPoolAssignmentCreateRequest {
  tenant_id: string;
  tenant_label?: string | null;
  is_default: boolean;
  max_channels?: number | null;
  reserved_channels?: number | null;
}
export interface AdminSIPTrunkPoolAssignmentPatchRequest {
  tenant_label?: string | null;
  is_default?: boolean;
  is_active?: boolean;
  max_channels?: number | null;
  reserved_channels?: number | null;
}
export type AdminSIPSyncResponse = ApiSchema["AdminSIPSyncResponse"];
export type AdminSystemHealthResponse = ApiSchema["AdminSystemHealthResponse"];
export type PlatformHealthResponse = ApiSchema["HealthResponse"];
export type AdminSystemConfigResponse = ApiSchema["AdminSystemConfigResponse"];
export type AdminSystemQuotaResponse = ApiSchema["AdminSystemQuotaResponse"];
export type AdminSystemFeatureFlagsResponse = ApiSchema["AdminSystemFeatureFlagsResponse"];
export type AdminSystemQuotaPatchRequest = ApiSchema["AdminSystemQuotaPatchRequest"];
export type AdminSystemFeatureFlagsPatchRequest =
  ApiSchema["AdminSystemFeatureFlagsPatchRequest"];

export interface ProviderCostMetadataResponse {
  cost_per_input_token_microcents?: number | null;
  cost_per_output_token_microcents?: number | null;
  cost_per_audio_second_microcents?: number | null;
  cost_per_character_microcents?: number | null;
  cost_per_request_microcents?: number | null;
}

export interface ProviderCredentialStateResponse {
  credential_source: string;
  validation_status: string;
  validated_at?: string | null;
  validation_error?: string | null;
  updated_at?: string | null;
  has_stored_secret: boolean;
}

export interface AdminProviderAssignedTenantResponse {
  tenant_id: string;
  tenant_display_name: string;
  enabled: boolean;
}

export interface AdminProviderSummaryResponse {
  provider_id: string;
  vendor: string;
  model: string;
  capability: string;
  label?: string | null;
  user_created?: boolean;
  runtime_scopes: string[];
  supports_tenant_credentials: boolean;
  supports_platform_credentials: boolean;
  credential_source: string;
  configured: boolean;
  available: boolean;
  availability_status: string;
  tenant_assignment_count: number;
  assigned_tenant?: AdminProviderAssignedTenantResponse | null;
  cost_metadata: ProviderCostMetadataResponse;
  platform_credential?: ProviderCredentialStateResponse | null;
}

export interface AdminProviderCreateRequest {
  capability: string;
  vendor: string;
  model: string;
  label?: string | null;
  api_key: string;
}

export interface AdminProviderUpdateRequest {
  label?: string | null;
}

export interface AdminProviderDeleteResponse {
  provider_id: string;
  deleted: boolean;
}

export interface AdminProviderAssignRequest {
  tenant_id: string;
}

export interface AdminProvidersListResponse {
  items: AdminProviderSummaryResponse[];
  total: number;
}

export interface AdminProviderAssignmentResponse {
  tenant_id: string;
  provider_id: string;
  tenant_display_name: string;
  enabled: boolean;
  is_default: boolean;
  effective_credential_source: string;
  updated_at: string;
}

export interface AdminProviderAssignmentsListResponse {
  items: AdminProviderAssignmentResponse[];
  total: number;
}

export interface AdminProviderQuotaPolicyResponse {
  quota_policy_id: string;
  tenant_id: string;
  provider_id: string;
  tenant_display_name: string;
  metric: string;
  limit_per_day: number;
  soft_limit_pct: number;
  updated_at: string;
}

export interface AdminProviderQuotaPoliciesListResponse {
  items: AdminProviderQuotaPolicyResponse[];
  total: number;
}

export interface AdminProviderUsageResponse {
  window_start: string;
  window_end: string;
  item: TenantProviderUsageSummaryResponse;
}

export interface AdminProviderQuotaResponse {
  window_start: string;
  window_end: string;
  item: TenantProviderQuotaSummaryResponse;
}

export interface AdminProviderCredentialWriteRequest {
  secret_fields: Record<string, string>;
}

export interface AdminProviderCredentialMutationResponse {
  provider_id: string;
  credential_source: string;
  validation_status: string;
  validated_at?: string | null;
  validation_error?: string | null;
  updated_at?: string | null;
}

export interface AdminProviderQuotaPolicyWriteRequest {
  tenant_id: string;
  metric: string;
  limit_per_day: number;
  soft_limit_pct?: number;
}

export interface AdminProviderQuotaPolicyMutationResponse {
  provider_id: string;
  tenant_id: string;
  metric: string;
  applied: boolean;
}

export interface AdminTenantProviderAssignRequest {
  provider_id: string;
  is_default?: boolean;
}

export interface AdminTenantProviderAssignmentMutationResponse {
  tenant_id: string;
  provider_id: string;
  enabled: boolean;
  is_default: boolean;
}

export type TenantSIPPoolResponse = ApiSchema["TenantSIPPoolResponse"];
export type TenantSIPPoolsListResponse = ApiSchema["TenantSIPPoolsListResponse"];
export type TenantSIPPoolPatchRequest = ApiSchema["TenantSIPPoolPatchRequest"];

// ---------------------------------------------------------------------------
// Audit types
// ---------------------------------------------------------------------------

export type AuditEvent = ApiSchema["AuditEventResponse"];

export interface AuditFilters {
  action?: string;
  resourceType?: string;
  actorId?: string;
  fromTs?: string;
  toTs?: string;
  limit?: number;
}

// ---------------------------------------------------------------------------
// Schedule types
// ---------------------------------------------------------------------------

export type MisfirePolicy = ApiSchema["MisfirePolicy"];

type ApiScheduleResponse = ApiSchema["ScheduleResponse"];

export type ScheduleResponse = ApiScheduleResponse & {
  ai_scenario_id?: string | null;
  name?: string | null;
  retry_on_failure?: boolean;
  consecutive_failures?: number;
  last_run_outcome?: string | null;
};

type ApiScheduleCreateRequest = ApiSchema["ScheduleCreate"];

export type ScheduleCreateRequest = ApiScheduleCreateRequest & {
  ai_scenario_id?: string | null;
  name?: string | null;
  retry_on_failure?: boolean;
};

type ApiSchedulePatchRequest = ApiSchema["SchedulePatch"];

export type SchedulePatchRequest = ApiSchedulePatchRequest & {
  ai_scenario_id?: string | null;
  name?: string | null;
  retry_on_failure?: boolean;
};

export type SchedulePreviewResponse = ApiSchema["SchedulePreviewResponse"];

// ---------------------------------------------------------------------------
// Pack types
// ---------------------------------------------------------------------------

export type ScenarioPackSummary = ApiSchema["ScenarioPackSummaryResponse"];

type ApiScenarioPackDetail = ApiSchema["ScenarioPackDetailResponse"];
type ApiScenarioPackItem = ApiSchema["ScenarioPackItemResponse"];
type ApiScenarioPackUpsert = ApiSchema["ScenarioPackUpsert"];

export type ScenarioPackItem = ApiScenarioPackItem & {
  ai_scenario_id?: string | null;
};

export type ScenarioPackDetail = Omit<ApiScenarioPackDetail, "items"> & {
  items: ScenarioPackItem[];
};

export type ScenarioPackUpsertRequest = ApiScenarioPackUpsert & {
  items?: Array<{
    scenario_id?: string | null;
    ai_scenario_id?: string | null;
  }>;
};

export type PackRunSummary = ApiSchema["PackRunSummaryResponse"] & {
  transport_profile_id?: string | null;
  dial_target?: string | null;
};

export type PackRunDetail = ApiSchema["PackRunDetailResponse"] & {
  transport_profile_id?: string | null;
  dial_target?: string | null;
};

export type PackRunFailureCategory = "dispatch_error" | "run_error" | "gate_blocked";

export type PackRunChildSummary = Omit<
  ApiSchema["PackRunChildSummaryResponse"],
  "failure_category"
> & {
  ai_scenario_id?: string | null;
  failure_category?: PackRunFailureCategory | null;
};

export interface PackAiLatencySummary {
  ai_runs: number;
  reply_gap_p95_ms?: number | null;
  bot_turn_duration_p95_ms?: number | null;
  harness_playback_p95_ms?: number | null;
}

export type PackRunChildrenResponse = Omit<ApiSchema["PackRunChildrenResponse"], "items"> & {
  ai_latency_summary?: PackAiLatencySummary | null;
  items: PackRunChildSummary[];
};

export type PackRunStartResponse = ApiSchema["PackRunStartResponse"];

export type PackRunCancelResponse = ApiSchema["PackRunCancelResponse"];

export interface PackRunMarkFailedResponse {
  pack_run_id: string;
  applied: boolean;
  state: string;
  reason: string;
}


// ---------------------------------------------------------------------------
// Playground types
// ---------------------------------------------------------------------------

export type PlaygroundExtractedTool = ApiSchema["PlaygroundExtractedTool"];
