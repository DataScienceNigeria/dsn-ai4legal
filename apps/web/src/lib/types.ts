export type Me = {
  id: string;
  name: string;
  email: string;
  initials: string;
  roles: string[];
  entities: string[];
  step_up_valid: boolean;
  /*
    False when the module is switched off as well as when the role carries no
    factor. Either way nothing is wanted from this person, which is the only
    thing the interface needs to know.
  */
  mfa_required: boolean;
  mfa_enrolled: boolean;
};

export type Sla = {
  target_hours: number | null;
  elapsed_hours: number;
  running: boolean;
  breached: boolean;
  near_breach: boolean;
  remaining_hours: number | null;
};

export type CounterpartyBrief = {
  id: string;
  reference: string;
  legal_name: string;
  relationship_class: string;
};

export type Matter = {
  id: string;
  number: string;
  entity: string;
  title: string;
  practice_code: string;
  risk_tier: string;
  status: string;
  next_action: string | null;
  due_date: string | null;
  blocker: string | null;
  privacy_flag: boolean;
  restricted: boolean;
  responsible_lawyer_id: string | null;
  counterparty: CounterpartyBrief | null;
  days_open: number;
  sla: Sla | null;
  classification?: string;
  tier_rationale?: string[];
  tier_overridden?: boolean;
  tier_override_reason?: string | null;
  value_amount?: number | null;
  value_currency?: string;
  permitted_transitions?: string[];
  created_at?: string;
};

export type TriageRow = {
  request_id: string;
  reference: string;
  entity: string;
  request_type: string;
  counterparty: string | null;
  privacy_flag: boolean;
  age_hours: number;
  suggested_tier: string;
  required_date: string | null;
  subject: string;
};

export type RequestAnswer = { name: string; label: string; value: string };

export type AttachmentBrief = {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  scan_status: string;
};

export type RequestDetail = {
  id: string;
  reference: string;
  entity: string;
  request_type: string;
  subject: string;
  purpose: string | null;
  requester_name: string | null;
  requester_email: string | null;
  proposed_counterparty: string | null;
  required_date: string | null;
  value_amount: number | null;
  value_currency: string;
  personal_data: boolean;
  special_category_data: boolean;
  third_party_confidential: boolean;
  leaves_nigeria: boolean;
  status: string;
  submitted_at: string;
  answers: RequestAnswer[];
  attachments: AttachmentBrief[];
};

export type TriageProposal = {
  tier: string;
  tier_rationale: string[];
  tier_1_eligible: boolean;
  triggers_privacy_assessment: boolean;
  proposed_owner: string | null;
  owner_rationale: string | null;
  request: RequestDetail | null;
};

export type RequestType = {
  id: string;
  code: string;
  business_label: string;
  description: string | null;
  agreement_type: string;
  practice_code: string;
  fields: FieldDefinition[];
  mandatory_fields: string[];
  sla_hours: number;
  sort_order: number;
};

export type BriefSection = {
  key: string;
  letter: string;
  title: string;
  intent: string;
};

export type FieldDefinition = {
  name: string;
  label: string;
  type: string;
  section?: string | null;
  help_text?: string | null;
  unit?: string | null;
  options?: string[];
  mandatory: boolean;
  condition?: string | null;
  progressive?: boolean;
  pattern?: string | null;
};

export type TimelineEntry = {
  stage: string;
  label: string;
  occurred_at: string | null;
  current: boolean;
  owner_first_name: string | null;
};

export type AwaitingConfirmation = {
  approval_id: string;
  document_id: string;
  document_name: string;
  step_name: string;
  due_at: string | null;
  changes_requested: string | null;
};

export type DraftBlock = { number: string; heading: string; text: string };

export type DraftForConfirmation = {
  reference: string;
  subject: string;
  document_name: string;
  generated_at: string | null;
  blocks: DraftBlock[];
  approval_id: string;
  step_name: string;
  changes_requested: string | null;
};

export type RequestStatus = {
  id: string;
  reference: string;
  subject: string;
  status: string;
  stage_label: string;
  owner_first_name: string | null;
  expected_date: string | null;
  last_update: string;
  matter_number: string | null;
  timeline: TimelineEntry[];
  awaiting_confirmation: AwaitingConfirmation | null;
};

export type Block = {
  key: string;
  number: string;
  heading: string;
  text: string;
  provenance: string;
  source_reference: string | null;
  novel: boolean;
};

export type Check = { name: string; passed: boolean; detail: string; items: string[] };

export type DocumentRecord = {
  id: string;
  matter_id: string | null;
  name: string;
  document_type: string;
  version: number;
  template_version_ref: string | null;
  clause_versions: string[];
  content_hash: string;
  classification: string;
  immutable: boolean;
  novel_clause_count: number;
  open_items: string[];
  blocks: Block[];
  consistency_checks: Check[];
  generated_at: string | null;
  signed_copy_held: boolean;
};

export type Approval = {
  id: string;
  step_index: number;
  step_name: string;
  step_mode: string;
  approver_id: string | null;
  approver_role: string | null;
  decision: string;
  comments: string | null;
  document_hash: string;
  due_at: string | null;
  decided_at: string | null;
  invalidated_by_event: string | null;
  actionable: boolean;
  approver_name: string | null;
  notes: string[];
};

export type Finding = {
  id: string;
  sequence: number;
  title: string;
  their_reference: string | null;
  clause_absent: boolean;
  severity: string;
  clause_category: string | null;
  clause_version_ref: string | null;
  their_text: string | null;
  house_position: string | null;
  suggested_redline: string | null;
  required_authority: string;
  matches_preapproved_fallback: boolean;
  decision: string;
  decided_at: string | null;
  clearance_rule: string | null;
  edited_text: string | null;
  document_id: string | null;
  block_key: string | null;
  round: number;
  carried_from_id: string | null;
  settled_in_round: number | null;
};

/*
  What changed between one pass over their paper and the next.

  `newly_raised` is the number that pays for rounds: a point appearing for the
  first time in a later round is something the counterparty altered while the
  argument was about something else, and no checklist catches it.
*/
export type RoundSummary = {
  round: number;
  document_id: string | null;
  document_name: string | null;
  total: number;
  settled: number;
  still_open: number;
  newly_raised: number;
};

export type Obligation = {
  id: string;
  reference: string;
  name: string;
  description: string | null;
  obligation_type: string;
  source_clause: string | null;
  source_quote: string | null;
  owner_id: string | null;
  due_date: string | null;
  recurrence: string;
  lead_time_days: number;
  evidence_required: boolean;
  evidence_reference: string | null;
  status: string;
  completed_at: string | null;
  decision_options: string[];
  decision_taken: string | null;
  contract_id: string | null;
  days_until_due: number | null;
  overdue: boolean;
  matter_id: string | null;
  contract_reference: string | null;
  counterparty_name: string | null;
  matter_number: string | null;
};

export type Contract = {
  id: string;
  reference: string;
  matter_id: string;
  entity: string;
  agreement_type: string;
  effective_date: string | null;
  end_date: string | null;
  renewal_type: string;
  notice_period_days: number | null;
  value_amount: number | null;
  value_currency: string;
  governing_law: string;
  signature_status: string;
  executed_at: string | null;
  content_hash: string | null;
  authoritative: boolean;
  executed_outside_platform: boolean;
  counterparty: CounterpartyBrief | null;
  matter_number: string | null;
  status: string;
  user_department: string | null;
  contract_owner_name: string | null;
  payment_terms: string | null;
  key_deliverables: string | null;
  termination_deadline: string | null;
  remarks: string | null;
  amends_contract_id: string | null;
  amends_reference: string | null;
  open_issue_count: number;
  open_change_count: number;
};

export type Fallback = {
  rank: number;
  text: string;
  required_authority: string;
  conditions?: string | null;
};

export type ClauseVersion = {
  id: string;
  reference: string;
  major: number;
  minor: number;
  status: string;
  house_position: string;
  fallbacks: Fallback[];
  unacceptable_position: string | null;
  usage_conditions: string | null;
  risk_notes: string | null;
  approval_date: string | null;
  effective_date: string | null;
  review_date: string | null;
};

export type Clause = {
  id: string;
  category: string;
  name: string;
  owner_id: string | null;
  entity_applicability: string[];
  jurisdiction: string;
  required_for_types: string[];
  current: ClauseVersion | null;
  versions: ClauseVersion[];
};

export type TemplatePlaceholder = {
  label: string;
  name: string;
  fact: string | null;
  supplied: boolean;
};

export type TemplateVersion = {
  id: string;
  reference: string;
  major: number;
  minor: number;
  status: string;
  body: Record<string, unknown>[];
  variables: Record<string, unknown>[];
  clause_references: string[];
  placeholders: TemplatePlaceholder[];
  approval_date: string | null;
  effective_date: string | null;
  review_date: string | null;
  change_summary: string | null;
  import_id?: string | null;
};

export type Template = {
  id: string;
  code: string;
  name: string;
  agreement_type: string;
  owner_id: string | null;
  entity_applicability: string[];
  jurisdiction: string;
  current: TemplateVersion | null;
  versions: TemplateVersion[];
};

export type ExtractedValue = {
  id: string;
  field_name: string;
  value: string;
  source_sentence: string;
  confidence: number | null;
  decision: string;
  corrected_value: string | null;
};

export type MailAttachment = {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  scan_status: string;
  created_at: string;
};

export type Communication = {
  id: string;
  entity: string;
  sender: string;
  subject: string;
  body: string;
  received_at: string;
  classification: string | null;
  classification_confidence: number | null;
  classification_corrected: boolean;
  corrected_classification: string | null;
  implied_work: boolean;
  implied_work_phrase: string | null;
  awaiting_response_since: string | null;
  matter_id: string | null;
  proposed_acknowledgment: string | null;
  proposed_matter_type: string | null;
  proposed_priority: string | null;
  proposed_owner_id: string | null;
  handled: boolean;
  injection_flagged: boolean;
  quarantined: boolean;
  age_days: number;
  extracted_values: ExtractedValue[];  attachments: MailAttachment[];
};

export type Source = { reference: string; kind: string; detail: string | null; quote: string | null };

export type Answer = {
  interaction_id: string;
  question: string;
  answer: string;
  sources: Source[];
  note: string | null;
  refused: boolean;
  refusal_reason: string | null;
  suppressed_statements: number;
};

export type ConversationTurn = {
  id: string;
  sequence: number;
  question: string;
  answer: Answer | null;
  created_at: string;
};

export type ConversationBrief = {
  id: string;
  entity: string;
  title: string;
  matter_id: string | null;
  matter_number: string | null;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
};

export type Conversation = ConversationBrief & { turns: ConversationTurn[] };

export type Capability = {
  id: string;
  code: string;
  name: string;
  module: string;
  purpose: string;
  max_data_class: string;
  tier_ceiling: string;
  human_requirement: string;
  confirming_role: string;
  state: string;
  disabled_reason: string | null;
  disabled_for_types: string[];
  metric_name: string;
  gate_expression: string;
  gate_threshold: number | null;
  last_score: number | null;
  last_score_label: string | null;
  last_evaluated_at: string | null;
  golden_set: string | null;
  gate_enforced: boolean;
  passes_gate: boolean;
  gate_status: string;
};

export type AiInteraction = {
  id: string;
  interaction_id: string;
  capability_code: string;
  entity: string;
  matter_id: string | null;
  data_class: string;
  provider: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  latency_ms: number;
  human_decision: string;
  shadow: boolean;
  injection_detected: boolean;
  refused: boolean;
  refusal_reason: string | null;
  created_at: string;
  retrieved_sources: { reference: string; kind: string }[];
};

export type DpiaImport = {
  filename: string;
  found: number;
  total: number;
  answers: Record<string, unknown>;
  imported_fields: string[];
  missing: string[];
  unmatched: string[];
  note: string;
};

export type Assessment = {
  id: string;
  reference: string;
  assessment_type: string;
  title: string;
  entity: string;
  stage: string;
  stage_records: {
    stage: string;
    owner_label?: string;
    status: string;
    completed_at?: string | null;
    notes?: string | null;
    completed_by?: string;
  }[];
  captured: Record<string, unknown>;
  imported_fields: string[];
  imported_from: string | null;
  risks: { risk: string; likelihood: string; impact: string; control: string }[];
  controls: { control: string; status: string }[];
  testing_evidence: { test: string; result: string; date: string }[];
  conditions: { name: string; detail: string; satisfied: boolean; due_date?: string }[];
  residual_risk_decision: string | null;
  residual_risk_reason: string | null;
  residual_risk_owner_id: string | null;
  approved_at: string | null;
  review_date: string | null;

  raised_by_id: string | null;
  submitted_at: string | null;
  dpo_review: Record<string, DpoSectionReview>;
  final_decision: string | null;
  final_decision_reason: string | null;
};

export type OperationalReport = {
  generated_at: string;
  entity: string;
  open_matters: number;
  by_tier: Record<string, number>;
  by_status: Record<string, number>;
  ageing: { label: string; count: number }[];
  sla_breaches: number;
  near_breaches: number;
  blocked: number;
  by_owner: { owner_id: string | null; owner_name: string; open_matters: number; breached: number }[];
  turnaround_median_hours: number | null;
  obligations_overdue: number;
  reviews_overdue: number;
};

export type KpiRow = {
  code: string;
  name: string;
  unit: string;
  measurement_method: string;
  baseline: number | null;
  baseline_captured_on: string | null;
  current: number | null;
  phase_1_target: number | null;
  phase_3_target: number | null;
  direction: string;
  on_track: boolean | null;
};

export type WeeklyUpdate = {
  generated_at: string;
  entity: string;
  period_start: string;
  period_end: string;
  delivery: string[];
  volumes: string[];
  turnaround: string[];
  blockers: string[];
  next_actions: string[];
};

export type UserRow = {
  id: string;
  name: string;
  work_email: string;
  roles: string[];
  entities: string[];
  specialisms: string[];
  workload: number;
  workload_ceiling: number;
  active: boolean;
  mfa_enrolled: boolean;
  last_login: string | null;
};

export type ExposureReport = {
  entities: string[];
  deviations_accepted: number;
  by_severity: Record<string, number>;
  by_authority: Record<string, number>;
  clauses_conceded: { clause_category: string; conceded: number; critical_or_material: number }[];
  unusual_liability_positions: {
    reference: string;
    agreement_type: string;
    value_amount: number | null;
    value_currency: string;
    reason: string;
  }[];
  note: string;
};

export type DeviationPattern = {
  clause_category: string;
  counterparty_class: string;
  challenged: number;
  accepted: number;
  rejected: number;
  undecided: number;
  absent: number;
  concession_rate: number | null;
};

export type InboxAccuracy = {
  window_days: number;
  messages: number;
  correction_rate: number | null;
  categories: {
    category: string;
    suggested: number;
    confirmed: number;
    false_positive: number;
    false_negative: number;
    precision: number | null;
    recall: number | null;
  }[];
  gate: string;
};

export type ComplianceItem = {
  id: string;
  requirement: string;
  statutory_reference: string | null;
  jurisdiction: string;
  filing_date: string | null;
  recurrence: string;
  accountable_owner_id: string | null;
  evidence_required: boolean;
  evidence_reference: string | null;
  filing_number: string | null;
  next_due_date: string | null;
  lead_time_days: number;
  version: number;
  effective_date: string | null;
  status: string;
  accountable_owner_name: string | null;
  due_soon_days: number;
};

export type CounterpartyRow = {
  id: string;
  reference: string;
  legal_name: string;
  trading_names: string[];
  counterparty_type: string;
  registration_number: string | null;
  domain: string | null;
  jurisdiction: string;
  relationship_class: string;
  risk_class: string;
  negotiation_notes: string | null;
  registered_address: string | null;
};

export type VendorRow = {
  id: string;
  counterparty_id: string;
  legal_name: string | null;
  security_review_status: string;
  security_review_date: string | null;
  open_security_findings: number;
  renewal_date: string | null;
  spend_band: string | null;
  assessment_expired: boolean;
};

export type RetentionRow = {
  record_class: string;
  retain_years: number;
  legal_hold: boolean;
  hold_reason: string | null;
  hold_set_at: string | null;
  deletion_requires_approval: boolean;
  description: string | null;
};

export type ConnectorRow = {
  code: string;
  name: string;
  purpose: string;
  direction: string;
  permitted_data_classes: string[];
  scopes: string[];
  review_date: string | null;
  owner: string | null;
  calls: number;
  active: boolean;
};

export type EgressRow = {
  id: string;
  occurred_at: string;
  connector_code: string;
  purpose: string;
  record_reference: string | null;
  data_class: string;
  result: string;
  detail: string | null;
};

export type ExportRow = {
  id: string;
  record_class: string;
  reason: string;
  data_classes: string[];
  status: string;
  created_at: string;
  decided_at: string | null;
};

export type DeletionRow = {
  id: string;
  record_class: string;
  object_reference: string;
  reason: string;
  status: string;
  certificate_reference: string | null;
  created_at: string;
  decided_at: string | null;
};

export type AuditRow = {
  id: string;
  sequence: number;
  occurred_at: string;
  actor_id: string | null;
  actor_label: string;
  entity: string | null;
  object_type: string;
  object_id: string | null;
  action: string;
  result: string;
  detail: string | null;
  before_state: Record<string, unknown> | null;
  after_state: Record<string, unknown> | null;
  ip_address: string | null;
  session_id: string | null;
  previous_digest: string | null;
  digest: string;
};

export type QualitySampleRow = {
  id: string;
  period: string;
  object_type: string;
  object_reference: string;
  reason: string;
  reviewed: boolean;
  outcome: string | null;
  notes: string | null;
  created_at: string;
};

export type NavCounts = {
  triage: number;
  matters: number;
  review: number;
  obligations: number;
  inbox: number;
  assessments: number;
  compliance: number;
  lifecycle: number;
};

export type SearchHit = {
  kind: string;
  label: string;
  reference: string;
  detail: string | null;
  href: string;
};

export type SearchResults = {
  query: string;
  hits: SearchHit[];
  searched_at: string;
};

export type NotificationItem = {
  id: string;
  kind: string;
  title: string;
  body: string | null;
  href: string | null;
  reference: string | null;
  created_at: string;
  read_at: string | null;
};

export type NotificationPage = {
  unread: number;
  notifications: NotificationItem[];
};

export type OrganisationRow = {
  id: string;
  entity_code: string;
  legal_name: string;
  trading_name: string | null;
  registration_number: string | null;
  tax_identification_number: string | null;
  registered_address: string | null;
  default_jurisdiction: string;
  contact_email: string | null;
  contact_phone: string | null;
  website: string | null;
  signatory_name: string | null;
  signatory_title: string | null;
  incomplete: string[];
};

/*
  The DPIA, as the platform serves it.

  The form definition arrives from the API rather than being written here, so a
  question added to the assessment appears in the portal without the interface
  being redeployed and neither copy can drift from the other.
*/
export type DpiaQuestion = {
  key: string;
  label: string;
  kind: "text" | "long_text" | "choice" | "multi_choice" | "boolean" | "date";
  help_text: string | null;
  options: string[];
  required: boolean;
  depends_on: string | null;
};

export type DpiaSection = {
  key: string;
  title: string;
  intent: string;
  assessed: boolean;
  questions: DpiaQuestion[];
};

export type DpiaForm = {
  sections: DpiaSection[];
  decisions: { key: string; label: string }[];
};

export type DpoSectionReview = {
  adequate: boolean;
  reasons: string;
  score: number;
  recommendations: string | null;
  responsibility: string | null;
  due_date: string | null;
  assessed_by: string;
  assessed_at: string;
};

export type ContractIssue = {
  id: string;
  entity: string;
  reference: string;
  contract_id: string;
  issue_type: string;
  severity: string;
  title: string;
  description: string;
  occurred_on: string | null;
  evidence_document_id: string | null;
  evidence_note: string | null;
  raised_by_name: string | null;
  assignee_id: string | null;
  assignee_name: string | null;
  status: string;
  resolution: string | null;
  resolved_at: string | null;
  change_request_id: string | null;
  outcome: string | null;
  outcome_matter_id: string | null;
  outcome_obligation_id: string | null;
  led_to: {
    kind: string;
    label: string;
    reference: string | null;
    href: string | null;
  } | null;
  settled: boolean;
  created_at: string;
  contract_reference: string | null;
  counterparty_name: string | null;
};

export type ChangeRequest = {
  id: string;
  entity: string;
  reference: string;
  contract_id: string;
  change_type: string;
  rationale: string;
  proposed_changes: string;
  financial_effect: string | null;
  value_delta: number | null;
  value_currency: string | null;
  financial_note: string | null;
  timeline_effect: string | null;
  proposed_end_date: string | null;
  timeline_note: string | null;
  requested_by_name: string | null;
  instrument: string | null;
  decision: string;
  decision_reason: string | null;
  decided_at: string | null;
  resulting_matter_id: string | null;
  created_at: string;
  contract_reference: string | null;
  counterparty_name: string | null;
  resulting_matter_number: string | null;
};

export type ClosureItem = {
  id: string;
  item_key: string;
  group_key: string;
  status: string;
  evidence_document_id: string | null;
  evidence_reference: string | null;
  note: string | null;
  confirmed_by_name: string | null;
  confirmed_at: string | null;
  label: string;
  intent: string;
  evidence_required: boolean;
  may_not_apply: boolean;
};

export type Closure = {
  contract_id: string;
  contract_reference: string;
  status: string;
  opened_at: string | null;
  closed_at: string | null;
  closure_note: string | null;
  settled: number;
  total: number;
  blocking: string[];
  groups: { key: string; title: string; intent: string; items: ClosureItem[] }[];
};

export type Term = { key: string; label: string };

export type Vocabulary = {
  agreement_types: Term[];
  issue_types: Term[];
  issue_statuses: Term[];
  issue_outcomes: Term[];
  change_types: Term[];
  instruments: Term[];
  change_decisions: Term[];
  contract_statuses: Term[];
  closure_statuses: Term[];
  severities: string[];
};

export type ConsultantReview = {
  id: string;
  entity: string;
  matter_id: string;
  document_id: string | null;
  consultant_id: string;
  consultant_name: string | null;
  brief: string;
  due_date: string | null;
  status: string;
  comments: string | null;
  returned_at: string | null;
  assessment: string | null;
  assessed_at: string | null;
  created_at: string;
  matter_number: string | null;
  matter_title: string | null;
  document_name: string | null;
};
