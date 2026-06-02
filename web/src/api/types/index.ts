export interface DriftCounts {
  target_drift: number;
  catalog_drift: number;
  package_drift: number;
  rule_drift: number;
  evidence_drift: number;
  discovery_drift: number;
  exception_drift: number;
}

export interface ComplianceSummary {
  total_evaluated: number;
  compliant_count: number;
  unknown_count: number;
  counts_by_drift_type: DriftCounts;
  filters_applied: Record<string, string>;
  as_of: string;
}

export interface ReadinessSummary {
  total_outside_target: number;
  ready_for_uplift_count: number;
  blocked_count: number;
  not_applicable_count: number;
  filters_applied: Record<string, string>;
  as_of: string;
  correlation_id: string;
}

export interface NetboxSummaryData {
  netbox_linked: number;
  csv_only: number;
  orphaned_in_gard: number;
  last_sync_at: string | null;
}

export interface NetboxSummaryEnvelope {
  data: NetboxSummaryData;
}

export interface AuditEvent {
  id: string;
  timestamp: string;
  actor: string;
  actor_type: string;
  action: string;
  object_type: string;
  object_id: string;
  result: string;
  correlation_id: string;
}

export interface AuditPage {
  items: AuditEvent[];
  next_cursor: string | null;
  total_returned: number;
}

export interface ComplianceEnvelope {
  state: string;
  summary: string;
  drift_type?: string | null;
  target_version?: string | null;
  observed_version?: string | null;
  reasons: { kind: string; detail?: string | null }[];
  recommended_actions?: RecommendedAction[];
  evaluated_at: string;
}

export interface RecommendedAction {
  kind: string;
  detail?: string | null;
  requires?: string[];
  target_version?: string | null;
  target_platform_family?: string | null;
}

export interface ComplianceDeviceRow {
  device_id: string;
  hostname: string;
  region?: string | null;
  site?: string | null;
  platform_family?: string | null;
  envelope: ComplianceEnvelope & { drift_type?: string | null };
}

export interface ComplianceDeviceList {
  items: ComplianceDeviceRow[];
  total_returned: number;
  next_page_token: string | null;
}

export interface DeviceFacts {
  id: string;
  hostname: string;
  site: string;
  serial_number?: string | null;
  region?: string | null;
  role?: string | null;
  management_ip?: string | null;
  vendor_normalized?: string | null;
  vendor_raw: string;
  model_normalized?: string | null;
  model_raw: string;
  platform_family?: string | null;
  lifecycle_state: string;
  source_system: string;
  updated_at: string;
}

export interface DeviceWithEnvelope {
  facts: DeviceFacts;
  envelope: { state: string; summary: string; confidence: number };
}

export interface DeviceList {
  items: DeviceWithEnvelope[];
  total_returned: number;
  next_page_token?: string | null;
}

export interface ReadinessEnvelope {
  state: string;
  summary: string;
  target_version?: string | null;
  observed_version?: string | null;
  blockers: { severity?: string; detail?: string }[];
  reasons: { kind: string; detail?: string | null }[];
  evaluated_at: string;
}

export interface EvaluateResponse {
  requested_count: number;
  evaluated_count: number;
  unchanged_count: number;
  correlation_id: string;
}

export interface ImportSummary {
  job_id: string;
  status: string;
  totals: {
    rows_total: number;
    rows_accepted: number;
    rows_rejected?: number;
    devices_created: number;
    devices_updated: number;
  };
}

export interface WritebackSummary {
  updated: number;
  skipped: number;
  unchanged: number;
  conflict: number;
  failed: number;
  skipped_not_linked: number;
}

export interface NetboxSyncReport {
  matched_count: number;
  created_count: number;
  updated_count: number;
  orphaned_count: number;
  ipam_alignment?: IpamAlignmentReport | null;
  writeback?: {
    phase: string;
    summary: WritebackSummary;
  } | null;
}

export interface IpamAlignmentSummary {
  devices_checked: number;
  aligned_count: number;
  mismatch_count: number;
  error_count: number;
  warning_count: number;
  info_count: number;
  findings_by_kind?: Record<string, number>;
  l2vpn_available?: boolean;
}

export interface IpamAlignmentReport {
  phase: string;
  run_id?: string | null;
  summary: IpamAlignmentSummary;
  entries?: Array<{
    device_id: string;
    netbox_device_id: number;
    overall_status: string;
    finding_count: number;
    top_kinds?: string[];
  }>;
}

export interface IpamAlignmentFinding {
  id: string;
  run_id: string;
  device_id: string;
  kind: string;
  severity: string;
  status: string;
  interface_name?: string | null;
  created_at: string;
}

export interface IpamAlignmentFindingList {
  items: IpamAlignmentFinding[];
  total_returned: number;
  next_page_token?: string | null;
}

export interface DeviceNetworkContextOut {
  device_id: string;
  netbox_device_id: number;
  resolved_mgmt_ip?: string | null;
  mgmt_resolution_method?: string | null;
  primary_ip4?: string | null;
  primary_ip6?: string | null;
  interfaces: Array<Record<string, unknown>>;
  overlay_bindings?: Array<Record<string, unknown>>;
  captured_at: string;
}

export interface NetboxSyncEnvelope {
  data: {
    run_id?: string;
    report?: NetboxSyncReport;
  };
}

export interface NetboxSyncRun {
  id: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  matched_count: number;
  created_count: number;
  updated_count: number;
  orphaned_count: number;
}

export interface NetboxSyncRunList {
  data: NetboxSyncRun[];
}

export interface WaveDeviceRow {
  device_id: string;
  hostname: string;
  position: number;
  snapshot_target_version?: string | null;
  snapshot_observed_version?: string | null;
}

export interface WaveEnvelope {
  id: string;
  plan_id: string;
  name: string;
  state: string;
  target_version: string;
  device_count: number;
  devices: WaveDeviceRow[];
  drafted_at: string;
  submitted_at: string | null;
}

export interface WaveList {
  items: WaveEnvelope[];
  total_returned: number;
  next_page_token: string | null;
}

export interface ExceptionEnvelope {
  id: string;
  device_id: string;
  state: string;
  justification: string;
  filed_at: string;
  expires_at: string;
}

export interface ExceptionList {
  items: ExceptionEnvelope[];
  total_returned: number;
}

export interface EvidenceItem {
  id: string;
  evidence_type: string;
  subject_type: string;
  subject_id: string;
  timestamp: string;
}

export interface EvidencePage {
  items: EvidenceItem[];
  total_returned: number;
}

export interface FirmwareTarget {
  id: string;
  name: string;
  platform_family: string;
  target_version: string;
  scope_selector: Record<string, string>;
  source_file_relpath: string;
  loaded_at: string;
}

export interface FirmwareTargetList {
  items: FirmwareTarget[];
  total_returned: number;
}

export interface CatalogReloadResponse {
  normalization_loaded: number;
  normalization_errors: string[];
  firmware_loaded: number;
  firmware_removed: number;
  devices_reevaluated: number;
}

export interface NormalizationRuleItem {
  id: string;
  priority: number;
  match: Record<string, unknown>;
  output: Record<string, unknown>;
  confidence: string;
  enabled: boolean;
  notes?: string | null;
}

export interface NormalizationRuleList {
  items: NormalizationRuleItem[];
  total_returned: number;
}

export interface ReadinessDeviceRow {
  device_id: string;
  hostname: string;
  region?: string | null;
  site?: string | null;
  platform_family?: string | null;
  envelope: ReadinessEnvelope;
}

export interface ReadinessDeviceList {
  items: ReadinessDeviceRow[];
  total_returned: number;
  next_page_token?: string | null;
}
