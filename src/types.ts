export interface AttachmentRecord {
  absolute_path?: string;
  exists?: boolean;
  mime_type?: string;
  name?: string;
  path?: string;
  url?: string;
}

export interface Ticket {
  assigned_agent: string;
  assignment_method: string;
  brand_tag: string;
  business_hours_tag: string;
  created_at: string;
  customer_email: string;
  intent_tag: string;
  issue: string;
  issue_type: string;
  priority: string;
  queue_name: string;
  status: string;
  ticket_id: string;
  unread_count: number;
  updated_at: string;
}

export interface TicketMessage {
  attachments: AttachmentRecord[];
  created_at: string;
  id: number;
  message: string;
  sender: string;
  ticket_id: string;
}

export interface TicketNote {
  attachments: AttachmentRecord[];
  author: string;
  created_at: string;
  id: number;
  note: string;
  ticket_id: string;
}

export interface TicketTag {
  color: string;
  created_at?: string;
  description: string;
  id: number;
  name: string;
  rule_id?: number | null;
  slug: string;
  source?: string;
  ticket_count?: number;
  updated_at?: string;
}

export interface Macro {
  category: string;
  created_at?: string;
  description?: string;
  id: number;
  is_archived?: number;
  last_used_at?: string | null;
  language?: string;
  name: string;
  response_text: string;
  set_status?: string;
  shortcut?: string;
  subject_template?: string;
  tag_names: string[];
  updated_at?: string;
  usage_count?: number;
}

export interface BusinessHoursRange {
  day_name: string;
  end_time: string;
  start_time: string;
}

export interface BusinessHoursProfile {
  created_at?: string;
  description: string;
  id: number;
  is_active?: number;
  is_default: number;
  name: string;
  ranges: BusinessHoursRange[];
  summary: string;
  timezone: string;
  updated_at?: string;
}

export interface WorkflowRuleCondition {
  field: string;
  id: string;
  operator: string;
  value: string;
}

export interface WorkflowRuleConfig {
  branch_conditions: WorkflowRuleCondition[];
  else_tag_ids: number[];
  event: string;
  match_tag_ids: number[];
  mode: "business_hours" | "custom";
  trigger_conditions: WorkflowRuleCondition[];
  version: number;
}

export interface WorkflowRule {
  builder_mode?: "business_hours" | "custom" | string;
  condition_field: string;
  condition_operator: string;
  config?: WorkflowRuleConfig;
  created_at?: string;
  description: string;
  else_tag_ids?: number[];
  event_name: string;
  false_tag_color?: string | null;
  false_tag_id?: number | null;
  false_tag_name?: string | null;
  id: number;
  is_enabled: number;
  match_tag_ids?: number[];
  name: string;
  rule_key?: string;
  true_tag_color?: string | null;
  true_tag_id?: number | null;
  true_tag_name?: string | null;
  updated_at?: string;
}

export interface TicketDetailResponse {
  messages: TicketMessage[];
  notes: TicketNote[];
  tags: TicketTag[];
  ticket: Ticket;
}

export interface SubscriptionRecord {
  amount?: string | number;
  frequency?: string;
  id?: string | number;
  next_billing_date?: string;
  price?: string | number;
  product_name?: string;
  status?: string;
  subscription_id?: string | number;
  [key: string]: any;
}

export interface CustomerProfileRecord {
  email?: string;
  name?: string;
  phone?: string;
  total_orders?: number | string;
  total_spent?: number | string;
  [key: string]: any;
}

export interface CustomerLookupResponse {
  customer?: CustomerProfileRecord;
  data?: {
    orders?: Order[];
  };
  orders?: Order[];
  source?: string;
  subscriptions?: SubscriptionRecord[];
}

export interface OrderItem {
  id?: string | number;
  name?: string;
  title?: string;
  product_title?: string;
  quantity?: number | string;
  qty?: number | string;
  price?: number | string;
  line_price?: number | string;
  subtotal?: number | string;
  total?: number | string;
  variant_title?: string;
  variant?: string;
  size?: string;
  image?: string;
  image_url?: string;
  thumbnail?: string;
  product_image?: string;
  featured_image?: string;
  [key: string]: any;
}

export interface Order {
  id?: string | number;
  order_number?: string;
  status?: string;
  total?: string | number;
  items?: OrderItem[];
  line_items?: OrderItem[];
  order_items?: OrderItem[];
  products?: OrderItem[];
  [key: string]: any;
}

export interface SupportWorkspaceUser {
  created_at?: string;
  email: string;
  id: number;
  name: string;
  role: "owner" | "admin" | "agent";
  status: "Active" | "Invited" | "Suspended";
  team: string;
  updated_at?: string;
}

export interface SupportArticleRecord {
  body: string;
  category: string;
  created_at?: string;
  id: number;
  keywords: string[];
  status: "Published" | "Draft";
  summary: string;
  title: string;
  updated_at?: string;
  url: string;
}

export interface KnowledgeDocumentRecord {
  body: string;
  category: string;
  created_at?: string;
  id: number;
  source_name: string;
  source_type: string;
  status: "Published" | "Draft";
  summary: string;
  tags: string[];
  title: string;
  updated_at?: string;
}

export interface KnowledgeUploadFileResult {
  document_count: number;
  file_name: string;
  warning?: string;
}

export interface KnowledgeUploadResponse {
  documents: KnowledgeDocumentRecord[];
  files: KnowledgeUploadFileResult[];
}

export interface KnowledgeUrlImportResponse {
  documents: KnowledgeDocumentRecord[];
  title: string;
  url: string;
  warning?: string;
}

export interface WorkflowRuleWindow {
  after_tag_name?: string | null;
  day_name: string;
  during_tag_name?: string | null;
  end_time: string;
  id?: number;
  is_enabled: number;
  rule_key: string;
  rule_name: string;
  sort_order: number;
  start_time: string;
  timezone: string;
  updated_at?: string;
  workflow_rule_id: number;
}

export interface RuleAffectedTicket {
  applied_tag?: string | null;
  business_hours_tag: string;
  created_at: string;
  customer_email: string;
  issue: string;
  priority: string;
  status: string;
  ticket_id: string;
}

export interface PropertyProject {
  id: number;
  projectName: string;
  city?: string;
  locality?: string;
  projectType?: string;
}

export interface PropertyWing {
  id: number;
  name: string;
  code?: string;
  constructionStatus?: string;
  totalFloors?: number;
}

export interface PropertyTypology {
  id: number;
  wingId: number;
  typologyName: string;
  typologyType?: string;
  carpetArea?: number;
  saleableArea?: number;
  minBasePrice?: number;
  rateType?: string;
  maxBasePrice?: number;
}

export interface PropertyInventoryUnit {
  id: number;
  wingId: number;
  typologyId: number;
  typologyName?: string;
  typologyType?: string;
  floorNumber?: number;
  unitNumber?: number | string;
  statusLabel?: string;
  carpetArea?: number;
  saleableArea?: number;
}
export interface CreateTicketResponse {
  assigned_agent: string;
  assignment_method: string;
  brand_tag: string;
  business_hours_tag: string;
  customer_email: string;
  customer_new: boolean;
  customer_vip: boolean;
  intent_tag: string;
  issue_type: string;
  priority: string;
  queue_name: string;
  ticket_id: string;
}

export interface SupportArticleMatch {
  body: string;
  category: string;
  id: number | string;
  keywords?: string[];
  score?: number;
  source: string;
  status?: "Published" | "Draft";
  summary: string;
  title: string;
  url: string;
}

export interface KnowledgeDocumentMatch {
  body: string;
  category: string;
  id: number;
  score?: number;
  source: string;
  source_name: string;
  source_type: string;
  status?: "Published" | "Draft";
  summary: string;
  tags: string[];
  title: string;
}

export interface SupportConversationMessage {
  sender: "bot" | "customer";
  text: string;
}

export interface SupportAssistChunkMatch {
  category: string;
  chunk_id: string;
  excerpt: string;
  record_id: number | string;
  record_kind: "article" | "knowledge" | string;
  score: number;
  source_name: string;
  source_type: string;
  title: string;
  url: string;
}

export interface DataApiCallTrace {
  cache_hit: boolean;
  created_at: string;
  duration_ms: number;
  endpoint: string;
  error: string;
  id: string;
  method: string;
  params: Record<string, string>;
  provider: string;
  response_summary: Record<string, unknown>;
  status: "cached" | "completed" | "failed" | string;
}
export interface RagEvaluationMetric {
  explanation: string;
  percent: number | null;
  score: number | null;
  status: "good" | "not_available" | "poor" | "review";
}

export interface RagEvaluation {
  evaluation_type: "online_proxy";
  evidence: {
    data_api_call_count: number;
    matched_chunk_count: number;
    relevant_chunk_count: number;
    successful_data_api_call_count: number;
  };
  metrics: Record<string, RagEvaluationMetric>;
  retrieval_mode: string;
  source_status: string;
  version: string;
}

export interface SupportAssistResponse {
  data_api_calls?: DataApiCallTrace[];
  agent_mode?: "fallback" | "qwen" | "retrieval";
  answer: string;
  articles: SupportArticleMatch[];
  assist_error?: string;
  confidence_label?: "high" | "low" | "medium";
  handoff_recommended?: boolean;
  knowledge_documents: KnowledgeDocumentMatch[];
  last_synced_at?: string | null;
  matched_chunks?: SupportAssistChunkMatch[];
  model?: string;
  offer_action_menu?: boolean;
  phone_rejection_reason?: string;
  quick_replies?: { label: string; value: string }[];
  rag_evaluation?: RagEvaluation;
  reply_language?: string;
  reply_script?: "latin" | "native";
  retrieval_mode?: "empty" | "lexical" | "semantic";
  source_label: string;
  source_status: "live" | "fallback" | "workspace";
  support_base_url: string;
  sync_error?: string;
  used_llm?: boolean;
}
