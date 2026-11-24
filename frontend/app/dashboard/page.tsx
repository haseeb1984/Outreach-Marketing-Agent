"use client";

import Link from "next/link";
import { BrandMark } from "../components/site-chrome";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type Workspace = { id: string; name: string; role: string };
type Prospect = { id: string; name: string; company: string; role?: string | null; contact_email?: string | null; contact_phone_e164?: string | null; website_url: string; evidence_url: string; fit_reason: string; stage: string; notes?: string | null; email_suppressed?: boolean; whatsapp_opt_in_documented?: boolean; whatsapp_opt_in_account_id?: string | null };
type Campaign = { id: string; name: string; client_business: string; client_offer: string; target_customer_profile: string; status?: string };
type FollowupSequence = { id: string; campaign_id: string; name: string; channel: string; status: string; enrollment_count?: number; active_count?: number; awaiting_approval_count?: number };
type FollowupEnrollment = { id: string; prospect_id: string; prospect_name?: string; company?: string; current_step: number; status: string; next_run_at?: string | null; current_draft_id?: string | null; current_delivery_id?: string | null; last_error_code?: string | null; pause_reason?: string | null };
type Draft = { id: string; subject?: string; body?: string; channel?: string; status: string; prospect_name?: string };
type DraftEvent = { event_type: string; note?: string | null; actor_id?: string | null; created_at?: string | null };
type Plan = { id: string; name: string; description: string; display_price: string | null; currency: string | null; billing_interval: string | null; checkout_available: boolean };
type Delivery = { id: string; subject?: string; channel?: string; status: string; error_code?: string | null; created_at?: string; scheduled_at?: string; provider_status?: string | null; provider_status_at?: string | null };
type Counts = Record<string, number>;
type CampaignPerformance = { id: string; name: string; status: string; counts: Counts };
type GrowthSchedule = { id: string; interval_hours: number; status: "active" | "paused"; next_run_at: string; last_enqueued_at?: string | null; last_attempted_at?: string | null; last_error_code?: string | null };
type GrowthJob = { id: string; job_type: string; status: string; error_code?: string | null; attempt_count: number; max_attempts: number; created_at: string; finished_at?: string | null };
type Project = { id: string; name: string; website_url?: string | null; business_model: string; target_market: string; language: string; audience: string; offer: string; conversion_goal: string; brand_voice: string; competitors: string[]; status: string };
type Invitation = { id: string; invited_email: string; role: string; status: string; expires_at: string; accepted_at?: string | null; revoked_at?: string | null };
type WorkspaceMember = { user_id: string; email: string; account_status?: string; email_verified_at?: string | null; last_login_at?: string | null; role: string; status: string; created_at: string; updated_at?: string };
type AuthSession = { id: string; created_at: string; last_seen_at: string; expires_at: string; user_agent?: string | null; is_current: boolean };
type EmailAccount = { id: string; workspace_id: string; label: string; smtp_host: string; smtp_port: number; smtp_username: string; from_email: string; from_name: string; starttls: boolean; status: string; created_at: string };
type WhatsAppAccount = { id: string; workspace_id: string; label: string; waba_id: string; phone_number_id: string; status: string; created_at: string };
type WhatsAppTemplate = { template_name: string; language_code: string; category: string; status: string; components?: Array<{ type?: string; format?: string; text?: string; buttons?: Array<{ type?: string; url?: string }> }>; provider_status?: string | null; verified_at?: string | null; updated_at?: string | null };
type WhatsAppConversation = { id: string; account_id: string; wa_id: string; account_label: string; assigned_to_user_id?: string | null; inbox_status?: "open" | "pending" | "resolved"; priority?: "low" | "normal" | "high" | "urgent"; prospect_name?: string | null; prospect_company?: string | null; last_message_text?: string | null; last_message_type?: string | null; last_message_at?: string | null; sla_state?: "within_sla" | "at_risk" | "overdue" | "met" | "resolved" | "not_applicable"; sla_due_at?: string | null; sla_started_at?: string | null; sla_first_response_at?: string | null; sla_paused_at?: string | null; sla_pause_reason?: string | null };
type WhatsAppInternalNote = { id: string; author_user_id: string; body: string; created_at: string };
type WhatsAppActivity = { id: string; actor_user_id: string; event_type: string; details?: Record<string, unknown>; created_at: string };
type WhatsAppSavedView = { id: string; name: string; filters: { inbox_status?: string; priority?: string; search?: string; assigned_to_me?: boolean; unassigned?: boolean; assigned_to_user_id?: string }; };
type WhatsAppMessage = { id: string; provider_message_id: string; message_type: string; text_body?: string | null; media_metadata?: Record<string, unknown>; media_mime_type?: string | null; media_filename?: string | null; media_size?: number | null; media_downloaded_at?: string | null; provider_timestamp?: string | null; received_at: string };
type UnifiedReplyThread = { id: string; prospect_id: string; prospect_name: string; prospect_company: string; contact_email?: string | null; contact_phone_e164?: string | null; channel: string; latest_message: string; provider: string; latest_direction?: string; latest_delivery_status?: string | null; latest_message_at: string; message_count: number };
type UnifiedReplyMessage = { id: string; channel: string; provider: string; direction: string; body: string; occurred_at: string; received_at: string; delivery_status?: string | null };
type WhatsAppWebhookEvent = { id: string; phone_number_id?: string | null; event_kind: string; received_at: string; processing_error_code?: string | null };
type Entitlement = { feature: string; allowed: boolean; reason: string; remaining: number | null };
type ResearchResult = { title: string; url: string; domain?: string; description: string; relevance_score?: number; relevance_reasons?: string[]; relevance_method?: string; evidence_type: string; requires_human_review: boolean };
type InfluencerCandidate = { profile_url: string; platform: string; title: string; description: string; relevance_score: number; relevance_reasons: string[]; requires_human_review: boolean; audience_metrics: null; audience_metrics_status: string };
type DomainChallenge = { domain: string; expires_at: string; dns_record: { record_name: string; record_value: string; type: string }; instructions: string };
type AuditFinding = { code: string; title: string; severity: string; occurrences: number; evidence_urls: string[] };
type WebsiteAudit = { report_id?: string; created_at?: string; report: { start_url: string; crawl_skipped: boolean; reason?: string; robots?: { status?: string; url?: string; error?: string }; crawl?: { pages_crawled: number; aggregate_findings: AuditFinding[]; pages: Array<{ final_url: string; title?: string | null; status_code: number; findings: Array<{ code: string; title: string; severity: string }> }> }; limitations?: string[] }; notice?: string };
type GrowthReviewReport = { report_type?: string; project_id?: string; project_name?: string; start_url: string; status?: string; crawl_summary?: { pages_crawled?: number }; competitor_discovery?: { status: string; notice?: string; count?: number; items?: Array<{ domain: string; title: string; url: string; description: string; matched_queries: string[]; relevance_score: number; competitor_status: string }> }; competitor_analysis?: { status: string; notice?: string; pages_checked?: number; pages_analyzed?: number; potential_gaps?: Array<{ query: string; classification: string; priority_score: number; confidence: string; client_coverage: number; competitor_coverage: number; competitor_evidence_url: string; client_evidence_urls: string[]; requires_human_review: boolean }> }; strategy?: { actions?: Array<{ id: string; title: string; priority: string; priority_score: number; recommended_action: string; evidence_url: string; confidence: string }>; measurement_plan?: string[] }; limitations?: string[]; review_required?: boolean };
type ContentBrief = { id: string; title: string; brief: string; target_keyword: string; status: string; evidence_url: string; article_title?: string; meta_title?: string; meta_description?: string; article_body?: string; article_status?: string; article_outline?: string[]; internal_link_suggestions?: Array<{url:string;reason:string}>; cms_status?: string; cms_post_id?: number | null; cms_post_url?: string | null };
type GrowthReviewResult = { report_id: string; workspace_id: string; project_id: string; project_name: string; report: GrowthReviewReport; created_at: string; notice: string };
type ApiResult<T> = { items: T[]; counts?: Counts; user?: { email: string; user_id: string }; csrf_token?: string | null; period_days?: number };

async function api<T>(path: string, csrf: string | null, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (options.method && !["GET", "HEAD", "OPTIONS"].includes(options.method.toUpperCase()) && csrf) headers.set("X-CSRF-Token", csrf);
  const response = await fetch(path, { ...options, headers, credentials: "same-origin", cache: "no-store" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : "";
    if (response.status === 401) throw new Error("Your session has expired. Please sign in again.");
    const messages: Record<string, string> = {
      workspace_not_found: "This workspace is not available to your account.",
      project_not_found: "This project is not available in the selected workspace.",
      authentication_not_configured: "The account service is not configured.",
      campaign_service_not_configured: "Campaign service is not available yet.",
      prospect_service_not_configured: "Prospect service is not available yet.",
      analytics_service_not_configured: "Analytics service is not available yet.",
      billing_service_not_configured: "Billing service is not available yet.",
      csrf_validation_failed: "Security check failed. Refresh the page and try again.",
      request_origin_rejected: "The frontend origin is not yet authorized by the backend.",
      email_provider_not_configured: "Email sending is not configured.",
      email_account_not_active: "Activate this SMTP account with a successful connection test before sending a diagnostic message.",
      email_account_changed_during_test: "SMTP settings changed while the connection test was running. Run the test again on the current credentials.",
      test_email_confirmation_required: "Confirm the diagnostic email send before continuing.",
      email_test_submission_failed: "The SMTP provider did not confirm diagnostic message submission.",
      quota_exhausted: "This workspace has reached its current usage limit.",
      search_provider_not_configured: "Live public-web research is not configured on the server yet.",
      search_provider_unavailable: "The search provider is temporarily unavailable. Try again later.",
      search_response_invalid: "The search provider returned an unexpected response.",
      whatsapp_account_not_active: "Choose an active, verified WhatsApp account in this workspace.",
      whatsapp_account_required_for_consent: "Choose the WhatsApp account covered by the documented consent.",
      whatsapp_opt_in_evidence_required: "Add an HTTPS URL to the consent evidence before saving opt-in.",
      invalid_prospect_stage: "Choose a valid CRM stage.",
      project_business_context_required: "Complete the project's business model and target market before running a growth review.",
      project_website_required: "Add a website URL to this project before running a growth review.",
      campaign_archived: "This campaign is archived, so its drafts cannot be queued or sent.",
      campaign_paused: "This campaign is paused, so new drafts and sends are blocked until it is resumed.",
      contact_replied: "This prospect has already replied. Further outreach is blocked to prevent unwanted follow-ups.",
      domain_not_verified: "Verify this website domain in the workspace before running a growth review.",
      website_domain_not_authorized: "Verify this website domain in the active workspace before scheduling scans.",
      growth_schedule_limit_reached: "This workspace already has 20 active recurring scans. Pause one before creating or resuming another.",
      growth_schedule_service_not_configured: "Recurring scan scheduling is not available until the database migration is applied.",
      workspace_job_service_not_configured: "Website-growth jobs are not available until the database migration is applied.",
      domain_authorization_not_configured: "Verify the website domain service configuration before scheduling a scan.",
      wordpress_site_must_be_public_https: "Use a public HTTPS WordPress site URL without credentials, query parameters, or a custom port.",
      wordpress_site_must_resolve_to_public_addresses: "The WordPress hostname must resolve only to public IP addresses.",
      wordpress_site_dns_unavailable: "The WordPress hostname could not be safely resolved. Check DNS and try again.",
      wordpress_authentication_failed: "WordPress rejected the application password. Check the username and create a new Application Password.",
      wordpress_user_lacks_post_capabilities: "The WordPress user needs permission to edit and publish posts.",
      wordpress_connection_not_pending: "Update the WordPress credentials before verifying this connection.",
      wordpress_article_or_connection_not_found: "No verified WordPress connection is available for this article's project. Verify its project site or configure the workspace default.",
      wordpress_site_change_blocked_by_existing_posts: "This WordPress connection already has linked posts. Keep the same site URL or use a separate project connection for another website.",
      article_editorial_approval_required: "Approve the article in the editorial workflow before sending it to WordPress.",
      explicit_publish_confirmation_required: "Confirm the public publishing action before continuing.",
      wordpress_draft_already_created: "This article already has a WordPress draft.",
      wordpress_draft_required_before_publish: "Send the article to WordPress as a draft before publishing it.",
      transfer_workspace_ownership_before_account_deletion: "Transfer ownership of shared workspaces before deleting this account.",

    };
    throw new Error(messages[detail] || "Request could not be completed (" + (detail || response.status) + ").");
  }
  return data as T;
}

function ErrorNotice({ message }: { message: string }) {
  return message ? <p className="notice" role="alert" aria-live="polite">{message}</p> : null;
}

export default function DashboardPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [csrf, setCsrf] = useState<string | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [emailAccounts, setEmailAccounts] = useState<EmailAccount[]>([]);
  const [whatsappAccounts, setWhatsappAccounts] = useState<WhatsAppAccount[]>([]);
  const [whatsappTemplates, setWhatsappTemplates] = useState<Record<string, WhatsAppTemplate[]>>({});
  const [whatsappConversations, setWhatsappConversations] = useState<WhatsAppConversation[]>([]);
  const [whatsappMessages, setWhatsappMessages] = useState<WhatsAppMessage[]>([]);
  const [whatsappNotes, setWhatsappNotes] = useState<WhatsAppInternalNote[]>([]);
  const [whatsappActivity, setWhatsappActivity] = useState<WhatsAppActivity[]>([]);
  const [whatsappFilterStatus, setWhatsappFilterStatus] = useState("");
  const [whatsappFilterPriority, setWhatsappFilterPriority] = useState("");
  const [whatsappFilterSearch, setWhatsappFilterSearch] = useState("");
  const [whatsappFilterAssignee, setWhatsappFilterAssignee] = useState("all");
  const [whatsappSavedViews, setWhatsappSavedViews] = useState<WhatsAppSavedView[]>([]);
  const [whatsappSavedViewsUnavailable, setWhatsappSavedViewsUnavailable] = useState(false);
  const [whatsappSLAUnavailable, setWhatsappSLAUnavailable] = useState(false);
  const [whatsappSLAWarningMinutes, setWhatsappSLAWarningMinutes] = useState(15);
  const [whatsappSLAPauseReason, setWhatsappSLAPauseReason] = useState("");
  const [whatsappSLABreachMinutes, setWhatsappSLABreachMinutes] = useState(60);
  const [whatsappSLASummary, setWhatsappSLASummary] = useState({ overdue: 0, at_risk: 0, within_sla: 0, paused: 0 });
  const [whatsappSavedViewName, setWhatsappSavedViewName] = useState("");
  const [whatsappSelectedSavedView, setWhatsappSelectedSavedView] = useState("");
  const [selectedWhatsAppBulkIds, setSelectedWhatsAppBulkIds] = useState<string[]>([]);
  const [whatsappBulkAssignee, setWhatsappBulkAssignee] = useState("__unchanged__");
  const [whatsappBulkStatus, setWhatsappBulkStatus] = useState("");
  const [whatsappBulkPriority, setWhatsappBulkPriority] = useState("");
  const [whatsappNoteDraft, setWhatsappNoteDraft] = useState("");
  const [whatsappDeadLetterEvents, setWhatsappDeadLetterEvents] = useState<WhatsAppWebhookEvent[]>([]);
  const [whatsappDeadLetterOffset, setWhatsappDeadLetterOffset] = useState(25);
  const [whatsappDeadLetterHasMore, setWhatsappDeadLetterHasMore] = useState(false);
  const [whatsappDeadLetterLoadingMore, setWhatsappDeadLetterLoadingMore] = useState(false);
  const [selectedWhatsAppConversation, setSelectedWhatsAppConversation] = useState("");
  const [unifiedReplyThreads, setUnifiedReplyThreads] = useState<UnifiedReplyThread[]>([]);
  const [selectedReplyProspectId, setSelectedReplyProspectId] = useState("");
  const [unifiedReplyMessages, setUnifiedReplyMessages] = useState<UnifiedReplyMessage[]>([]);
  const [unifiedReplyBusy, setUnifiedReplyBusy] = useState(false);
  const [replyDraftBody, setReplyDraftBody] = useState("");
  const [replyDraftSubject, setReplyDraftSubject] = useState("");
  const [whatsappInboxBusy, setWhatsappInboxBusy] = useState(false);
  const [whatsappLabel, setWhatsappLabel] = useState("");
  const [whatsappWabaId, setWhatsappWabaId] = useState("");
  const [whatsappPhoneNumberId, setWhatsappPhoneNumberId] = useState("");
  const [whatsappAccessToken, setWhatsappAccessToken] = useState("");
  const [selectedEmailAccountId, setSelectedEmailAccountId] = useState("");
  const [editingEmailAccountId, setEditingEmailAccountId] = useState<string | null>(null);
  const [emailAccountLabel, setEmailAccountLabel] = useState("");
  const [smtpHost, setSmtpHost] = useState("smtp.gmail.com");
  const [smtpUsername, setSmtpUsername] = useState("");
  const [smtpPassword, setSmtpPassword] = useState("");
  const [smtpFromEmail, setSmtpFromEmail] = useState("");
  const [smtpFromName, setSmtpFromName] = useState("Outreach Marketing Agent");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [projectName, setProjectName] = useState("");
  const [projectWebsite, setProjectWebsite] = useState("");
  const [projectBusinessModel, setProjectBusinessModel] = useState("");
  const [projectMarket, setProjectMarket] = useState("");
  const [projectLanguage, setProjectLanguage] = useState("");
  const [projectAudience, setProjectAudience] = useState("");
  const [projectOffer, setProjectOffer] = useState("");
  const [projectGoal, setProjectGoal] = useState("");
  const [projectBrandVoice, setProjectBrandVoice] = useState("");
  const [projectCompetitors, setProjectCompetitors] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [authSessions, setAuthSessions] = useState<AuthSession[]>([]);
  const [workspaceName, setWorkspaceName] = useState("");
  const [newWorkspaceName, setNewWorkspaceName] = useState("");
  const [prospects, setProspects] = useState<Prospect[]>([]);
  const [prospectSearch, setProspectSearch] = useState("");
  const [prospectStageFilter, setProspectStageFilter] = useState("all");
  const [crmOffset, setCrmOffset] = useState(0);
  const [crmTotal, setCrmTotal] = useState(0);
  const crmPageSize = 50;
  const [researchQuery, setResearchQuery] = useState("");
  const [researchResults, setResearchResults] = useState<ResearchResult[]>([]);
  const [researchBusy, setResearchBusy] = useState(false);
  const [influencerQuery, setInfluencerQuery] = useState("");
  const [influencerPlatforms, setInfluencerPlatforms] = useState(["instagram", "tiktok", "youtube", "linkedin", "x"]);
  const [influencerResults, setInfluencerResults] = useState<InfluencerCandidate[]>([]);
  const [influencerBusy, setInfluencerBusy] = useState(false);
  const [domainName, setDomainName] = useState("");
  const [domainChallenge, setDomainChallenge] = useState<DomainChallenge | null>(null);
  const [domainBusy, setDomainBusy] = useState(false);
  const [auditUrl, setAuditUrl] = useState("");
  const [auditReport, setAuditReport] = useState<WebsiteAudit | null>(null);
  const [auditHistory, setAuditHistory] = useState<Array<{ id: string; start_url: string; status: string; created_at: string }>>([]);
  const [auditBusy, setAuditBusy] = useState(false);
  const [growthReviewResult, setGrowthReviewResult] = useState<GrowthReviewResult | null>(null);
  const [contentBriefs, setContentBriefs] = useState<ContentBrief[]>([]);
  const [wordpressConnection, setWordPressConnection] = useState<{connected:boolean;inherited_from_workspace?:boolean;connection?:{id:string;site_url:string;username:string;status:string;project_id?:string|null}} | null>(null);
  const [wordpressBusy, setWordPressBusy] = useState(false);
  const [wordpressProjectId, setWordPressProjectId] = useState("");
  const [wordpressEditing, setWordPressEditing] = useState(false);
  const [editingArticleId, setEditingArticleId] = useState<string | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [followupSequences, setFollowupSequences] = useState<FollowupSequence[]>([]);
  const [followupEnrollments, setFollowupEnrollments] = useState<Record<string, FollowupEnrollment[]>>({});
  const [followupName, setFollowupName] = useState("");
  const [followupCampaignId, setFollowupCampaignId] = useState("");
  const [followupChannel, setFollowupChannel] = useState("email");
  const [followupStepsJson, setFollowupStepsJson] = useState(JSON.stringify([{ delay_minutes: 0, subject_template: "Following up with {{first_name}}", body_template: "Hi {{first_name}}, I wanted to follow up on my earlier note. Would a short conversation be useful?" }, { delay_minutes: 4320, subject_template: "One final note for {{company}}", body_template: "Hi {{first_name}}, one final follow-up from me. If this is not relevant, no action is needed." }], null, 2));
  const [followupProspectId, setFollowupProspectId] = useState("");
  const [followupResolutionReason, setFollowupResolutionReason] = useState<Record<string, string>>({});
  const [followupResolutionEvidence, setFollowupResolutionEvidence] = useState<Record<string, string>>({});
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [draftEvents, setDraftEvents] = useState<Record<string, DraftEvent[]>>({});
  const [draftHistoryOpen, setDraftHistoryOpen] = useState<Record<string, boolean>>({});
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [integrationStatus, setIntegrationStatus] = useState<{ email?: { configuration_complete: boolean; missing_fields: string[]; connection_tested?: boolean }; whatsapp?: { configuration_complete: boolean; missing_fields: string[]; live_send_enabled: boolean; dispatch_feature_enabled?: boolean; active_workspace_accounts?: number; webhook_endpoint?: string; reason?: string }; ai_outreach?: { configured: boolean; model?: string | null; generation_mode: string; human_approval_required: boolean; automatic_send: boolean } } | null>(null);
  const [integrationBusy, setIntegrationBusy] = useState(false);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [selectedPlan, setSelectedPlan] = useState("");
  const [counts, setCounts] = useState<Counts>({});
  const [campaignPerformance, setCampaignPerformance] = useState<CampaignPerformance[]>([]);
  const [campaignPerformanceUnavailable, setCampaignPerformanceUnavailable] = useState(false);
  const [growthSchedules, setGrowthSchedules] = useState<GrowthSchedule[]>([]);
  const [growthSchedulesUnavailable, setGrowthSchedulesUnavailable] = useState(false);
  const [growthJobs, setGrowthJobs] = useState<GrowthJob[]>([]);
  const [growthJobsUnavailable, setGrowthJobsUnavailable] = useState(false);
  const [growthJobReport, setGrowthJobReport] = useState<{ id: string; result: unknown } | null>(null);
  const [scheduleStartUrl, setScheduleStartUrl] = useState("");
  const [scheduleBusinessType, setScheduleBusinessType] = useState("");
  const [scheduleTargetMarket, setScheduleTargetMarket] = useState("");
  const [scheduleQueries, setScheduleQueries] = useState("");
  const [scheduleIntervalHours, setScheduleIntervalHours] = useState("168");
  const [entitlements, setEntitlements] = useState<Entitlement[]>([]);
  const [entitlementsUnavailable, setEntitlementsUnavailable] = useState(false);
  const [period, setPeriod] = useState("30");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const loadSequenceRef = useRef(0);
  const workspaceSwitchSequenceRef = useRef(0);
  const periodRef = useRef(period);
  const workspaceIdRef = useRef(workspaceId);
  const csrfRef = useRef(csrf);
  const replyDetailSequenceRef = useRef(0);
  const authSessionsSequenceRef = useRef(0);
  const replyDraftSequenceRef = useRef(0);
  const whatsappDetailSequenceRef = useRef(0);
  const whatsappConversationUpdateSequenceRef = useRef(0);
  const whatsappBulkUpdateSequenceRef = useRef(0);
  const whatsappInternalNoteSequenceRef = useRef(0);
  const whatsappMediaSequenceRef = useRef(0);
  const whatsappInboxQuerySequenceRef = useRef(0);
  const whatsappSavedViewsSequenceRef = useRef(0);
  const whatsappSLAActionSequenceRef = useRef(0);
  const whatsappSLALoadSequenceRef = useRef(0);
  const whatsappDeadLetterLoadSequenceRef = useRef(0);
  const whatsappDeadLetterLoadLockRef = useRef(false);
  const crmLoadSequenceRef = useRef(0);
  const whatsappBusyCountRef = useRef(0);
  const whatsappBusyEpochRef = useRef(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [campaignName, setCampaignName] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [offer, setOffer] = useState("");
  const [targetProfile, setTargetProfile] = useState("");
  const [selectedCampaign, setSelectedCampaign] = useState("");
  const [selectedProspect, setSelectedProspect] = useState("");
  const [draftChannel, setDraftChannel] = useState("email");
  const [draftCallToAction, setDraftCallToAction] = useState("");
  const [deliveryScheduleLocal, setDeliveryScheduleLocal] = useState("");
  const [prospectName, setProspectName] = useState("");
  const [prospectCompany, setProspectCompany] = useState("");
  const [prospectEmail, setProspectEmail] = useState("");
  const [prospectPhone, setProspectPhone] = useState("");
  const [prospectWebsite, setProspectWebsite] = useState("");
  const [evidenceUrl, setEvidenceUrl] = useState("");
  const [fitReason, setFitReason] = useState("");

  const loadWorkspaceData = useCallback(async (selectedId: string, token: string) => {
    if (!selectedId) return;
    crmLoadSequenceRef.current += 1;
    whatsappDeadLetterLoadSequenceRef.current += 1;
    whatsappDeadLetterLoadLockRef.current = false;
    setWhatsappDeadLetterLoadingMore(false);
    const loadSequence = ++loadSequenceRef.current;
    const isCurrentLoad = () => loadSequenceRef.current === loadSequence;
    setGrowthJobReport(null);
    // Load independent dashboard surfaces independently: one unavailable API must not blank the whole workspace.
    const primaryResults = await Promise.allSettled([
      api<ApiResult<Prospect>>("/api/v1/prospects?workspace_id=" + encodeURIComponent(selectedId) + "&limit=50", token),
      api<ApiResult<Campaign>>("/api/v1/campaigns?workspace_id=" + encodeURIComponent(selectedId) + "&limit=50", token),
      api<ApiResult<Draft>>("/api/v1/drafts?workspace_id=" + encodeURIComponent(selectedId) + "&status=all&limit=50", token),
      api<{ counts: Counts }>("/api/v1/analytics/summary?workspace_id=" + encodeURIComponent(selectedId) + "&since_days=" + periodRef.current, token),
      api<ApiResult<Delivery>>("/api/v1/deliveries?workspace_id=" + encodeURIComponent(selectedId) + "&limit=50", token),
      api<{ items: ContentBrief[] }>("/api/v1/content-briefs?workspace_id=" + encodeURIComponent(selectedId), token),
      api<{ connected:boolean; inherited_from_workspace?:boolean;connection?:{id:string;site_url:string;username:string;status:string;project_id?:string|null} }>("/api/v1/integrations/wordpress/connection?workspace_id=" + encodeURIComponent(selectedId), token),
    ]);
    if (!isCurrentLoad()) return;
    const [prospectResult, campaignResult, draftResult, analyticsResult, deliveryResult, contentBriefResult, wordpressResult] = primaryResults;
    const p = prospectResult.status === "fulfilled" ? prospectResult.value : { items: [] as Prospect[] };
    const c = campaignResult.status === "fulfilled" ? campaignResult.value : { items: [] as Campaign[] };
    const d = draftResult.status === "fulfilled" ? draftResult.value : { items: [] as Draft[] };
    const a = analyticsResult.status === "fulfilled" ? analyticsResult.value : { counts: {} as Counts };
    const deliveryData = deliveryResult.status === "fulfilled" ? deliveryResult.value : { items: [] as Delivery[] };
    setProspects(p.items || []);
    setCampaigns(c.items || []);
    setDrafts(d.items || []);
    setDeliveries(deliveryData.items || []);
    setContentBriefs(contentBriefResult.status === "fulfilled" ? (contentBriefResult.value.items || []) : []);
    setWordPressConnection(wordpressResult.status === "fulfilled" ? wordpressResult.value : null);
    setCounts(a.counts || {});
    const primaryFailureNames = ["prospects", "campaigns", "drafts", "analytics", "deliveries", "editorial briefs", "WordPress connection"].filter((_, index) => primaryResults[index].status === "rejected");
    const followupResult = await Promise.allSettled([api<{ items: FollowupSequence[] }>("/api/v1/follow-up-sequences?workspace_id=" + encodeURIComponent(selectedId), token)]);
    if (!isCurrentLoad()) return;
    setFollowupSequences(followupResult[0].status === "fulfilled" ? (followupResult[0].value.items || []) : []);
    setFollowupEnrollments({});
    const replyInboxResult = await Promise.allSettled([
      api<{ items: UnifiedReplyThread[] }>("/api/v1/conversations?workspace_id=" + encodeURIComponent(selectedId) + "&limit=50", token),
    ]);
    if (!isCurrentLoad()) return;
    const loadedReplyThreads = replyInboxResult[0].status === "fulfilled" ? (replyInboxResult[0].value.items || []) : [];
    setUnifiedReplyThreads(loadedReplyThreads);
    setSelectedReplyProspectId(current => loadedReplyThreads.some(thread => thread.prospect_id === current) ? current : "");
    if (!loadedReplyThreads.length) setUnifiedReplyMessages([]);
    const performanceResult = await Promise.allSettled([
      api<{ items: CampaignPerformance[] }>("/api/v1/analytics/campaigns?workspace_id=" + encodeURIComponent(selectedId) + "&since_days=" + periodRef.current + "&limit=50", token),
    ]);
    if (!isCurrentLoad()) return;
    setCampaignPerformance(performanceResult[0].status === "fulfilled" ? (performanceResult[0].value.items || []) : []);
    setCampaignPerformanceUnavailable(performanceResult[0].status !== "fulfilled");
    const scheduleResult = await Promise.allSettled([
      api<{ items: GrowthSchedule[] }>("/api/v1/workspace-growth-schedules?workspace_id=" + encodeURIComponent(selectedId), token),
    ]);
    if (!isCurrentLoad()) return;
    setGrowthSchedules(scheduleResult[0].status === "fulfilled" ? (scheduleResult[0].value.items || []) : []);
    setGrowthSchedulesUnavailable(scheduleResult[0].status !== "fulfilled");
    const jobResult = await Promise.allSettled([
      api<{ items: GrowthJob[] }>("/api/v1/workspace-jobs?workspace_id=" + encodeURIComponent(selectedId) + "&limit=20&offset=0", token),
    ]);
    if (!isCurrentLoad()) return;
    setGrowthJobs(jobResult[0].status === "fulfilled" ? (jobResult[0].value.items || []) : []);
    setGrowthJobsUnavailable(jobResult[0].status !== "fulfilled");
    const projectResult = await Promise.allSettled([
      api<ApiResult<Project>>("/api/v1/projects?workspace_id=" + encodeURIComponent(selectedId) + "&limit=50", token),
    ]);
    if (!isCurrentLoad()) return;
    const projectResponse = projectResult[0];
    setProjects(projectResponse.status === "fulfilled" ? (projectResponse.value.items || []) : []);
    const auditHistoryResult = await Promise.allSettled([api<{ items: Array<{ id: string; start_url: string; status: string; created_at: string }> }>("/api/v1/website-audits?workspace_id=" + encodeURIComponent(selectedId) + "&limit=10", token)]);
    if (!isCurrentLoad()) return;
    setAuditHistory(auditHistoryResult[0].status === "fulfilled" ? (auditHistoryResult[0].value.items || []) : []);
    const invitationResult = await Promise.allSettled([api<{ items: Invitation[] }>("/api/v1/workspaces/invitations?workspace_id=" + encodeURIComponent(selectedId), token)]);
    if (!isCurrentLoad()) return;
    setInvitations(invitationResult[0].status === "fulfilled" ? (invitationResult[0].value.items || []) : []);
    const memberResult = await Promise.allSettled([api<{ items: WorkspaceMember[] }>("/api/v1/workspaces/members?workspace_id=" + encodeURIComponent(selectedId), token)]);
    if (!isCurrentLoad()) return;
    setMembers(memberResult[0].status === "fulfilled" ? (memberResult[0].value.items || []) : []);
    const emailAccountResult = await Promise.allSettled([api<{ items: EmailAccount[] }>("/api/v1/integrations/email-accounts?workspace_id=" + encodeURIComponent(selectedId), token)]);
    if (!isCurrentLoad()) return;
    const loadedEmailAccounts = emailAccountResult[0].status === "fulfilled" ? (emailAccountResult[0].value.items || []) : [];
    setEmailAccounts(loadedEmailAccounts);
    setSelectedEmailAccountId(current => loadedEmailAccounts.some(account => account.id === current && account.status === "active") ? current : (loadedEmailAccounts.find(account => account.status === "active")?.id || ""));
    const whatsappAccountResult = await Promise.allSettled([api<ApiResult<WhatsAppAccount>>("/api/v1/integrations/whatsapp/accounts?workspace_id=" + encodeURIComponent(selectedId), token)]);
    if (!isCurrentLoad()) return;
    const loadedWhatsAppAccounts = whatsappAccountResult[0].status === "fulfilled" ? (whatsappAccountResult[0].value.items || []) : [];
    setWhatsappAccounts(loadedWhatsAppAccounts);
    const templateResults = await Promise.allSettled(loadedWhatsAppAccounts.map(account =>
      api<{ items: WhatsAppTemplate[] }>(
        "/api/v1/integrations/whatsapp/accounts/" + encodeURIComponent(account.id) + "/templates?workspace_id=" + encodeURIComponent(selectedId),
        token,
      ),
    ));
    if (!isCurrentLoad()) return;
    const loadedTemplates: Record<string, WhatsAppTemplate[]> = {};
    templateResults.forEach((result, index) => {
      if (result.status === "fulfilled") loadedTemplates[loadedWhatsAppAccounts[index].id] = result.value.items || [];
    });
    setWhatsappTemplates(loadedTemplates);
    const [inboxResult, webhookDeadLetterResult] = await Promise.allSettled([
      api<{ items: WhatsAppConversation[] }>("/api/v1/integrations/whatsapp/inbox/conversations?workspace_id=" + encodeURIComponent(selectedId) + "&limit=50", token),
      api<{ items: WhatsAppWebhookEvent[]; next_offset?: number | null; has_more?: boolean }>("/api/v1/integrations/whatsapp/inbox/webhook-events?workspace_id=" + encodeURIComponent(selectedId) + "&state=dead_letter&limit=25&offset=0", token),
    ]);
    if (!isCurrentLoad()) return;
    const loadedConversations = inboxResult.status === "fulfilled" ? (inboxResult.value.items || []) : [];
    setWhatsappConversations(loadedConversations);
    setWhatsappDeadLetterEvents(webhookDeadLetterResult.status === "fulfilled" ? (webhookDeadLetterResult.value.items || []) : []);
    setWhatsappDeadLetterOffset(webhookDeadLetterResult.status === "fulfilled" ? (webhookDeadLetterResult.value.next_offset ?? 25) : 25);
    setWhatsappDeadLetterHasMore(webhookDeadLetterResult.status === "fulfilled" && Boolean(webhookDeadLetterResult.value.has_more));
    setWhatsappDeadLetterLoadingMore(false);
    setSelectedWhatsAppConversation(current => {
      if (loadedConversations.some(item => item.id === current)) return current;
      setWhatsappMessages([]);
      return "";
    });

    const entitlementResults = await Promise.allSettled([
      api<Entitlement>("/api/v1/billing/entitlements?workspace_id=" + encodeURIComponent(selectedId) + "&feature=ai_draft_generations", token),
      api<Entitlement>("/api/v1/billing/entitlements?workspace_id=" + encodeURIComponent(selectedId) + "&feature=email_sends", token),
    ]);
    if (!isCurrentLoad()) return;
    const availableEntitlements = entitlementResults
      .filter((result): result is PromiseFulfilledResult<Entitlement> => result.status === "fulfilled")
      .map(result => result.value);
    setEntitlements(availableEntitlements);
    setEntitlementsUnavailable(availableEntitlements.length !== 2);
    const failedSections = [...primaryFailureNames];
    if (followupResult[0].status === "rejected") failedSections.push("follow-up automation");
    if (replyInboxResult[0].status === "rejected") failedSections.push("unified inbox");
    if (performanceResult[0].status === "rejected") failedSections.push("campaign analytics");
    if (scheduleResult[0].status === "rejected") failedSections.push("growth schedules");
    if (jobResult[0].status === "rejected") failedSections.push("growth jobs");
    if (projectResponse.status === "rejected") failedSections.push("projects");
    if (auditHistoryResult[0].status === "rejected") failedSections.push("website audit history");
    if (invitationResult[0].status === "rejected") failedSections.push("invitations");
    if (memberResult[0].status === "rejected") failedSections.push("team members");
    if (emailAccountResult[0].status === "rejected") failedSections.push("email accounts");
    if (whatsappAccountResult[0].status === "rejected") failedSections.push("WhatsApp accounts");
    if (templateResults.some(result => result.status === "rejected")) failedSections.push("WhatsApp message templates");
    if (inboxResult.status === "rejected") failedSections.push("WhatsApp inbox");
    if (webhookDeadLetterResult.status === "rejected") failedSections.push("webhook events");
    if (entitlementResults.some(result => result.status === "rejected")) failedSections.push("billing entitlements");
    if (failedSections.length) setError("Some workspace sections could not load (" + failedSections.join(", ") + "). Other sections remain available; use Refresh to retry.");
    // Load secondary inbox controls with the selected workspace so saved views and SLA
    // thresholds are immediately available after first load and every workspace switch.
    await Promise.all([loadWhatsAppSavedViews(selectedId, token), loadWhatsAppSLA(selectedId, token)]);
  }, []);

  const refresh = useCallback(async (selectedId = workspaceId, token = csrf) => {
    if (!selectedId || !token) return;
    setError("");
    const requestedLoad = loadSequenceRef.current + 1;
    setRefreshing(true);
    try {
      await loadWorkspaceData(selectedId, token);
    } catch (err) {
      if (loadSequenceRef.current === requestedLoad) setError(err instanceof Error ? err.message : "Workspace data could not be loaded.");
    } finally {
      if (loadSequenceRef.current === requestedLoad) setRefreshing(false);
    }
  }, [csrf, loadWorkspaceData, workspaceId]);

  useEffect(() => {
    periodRef.current = period;
    workspaceIdRef.current = workspaceId;
    csrfRef.current = csrf;
  }, [period, workspaceId, csrf]);

  useEffect(() => {
    const selectedId = workspaceIdRef.current;
    const token = csrfRef.current;
    if (selectedId && token) void loadWorkspaceData(selectedId, token);
  }, [period, loadWorkspaceData]);

  useEffect(() => {
    let cancelled = false;
    api<{ items: Plan[] }>("/api/v1/billing/paddle/plans", null)
      .then(result => {
        if (!cancelled) {
          const configured = result.items || [];
          setPlans(configured);
          setSelectedPlan(configured.find(plan => plan.checkout_available)?.id || configured[0]?.id || "");
        }
      })
      .catch(() => { if (!cancelled) setPlans([]); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const session = await api<{ user: { email: string }; csrf_token: string | null }>("/api/v1/auth/me", null);
        if (!session.csrf_token) throw new Error("Session security token is missing. Sign in again.");
        const result = await api<{ items: Workspace[] }>("/api/v1/workspaces", session.csrf_token);
        if (cancelled) return;
        setEmail(session.user.email);
        setCsrf(session.csrf_token);
        setWorkspaces(result.items || []);
        setWorkspaceName(result.items?.[0]?.name || "");
        const first = result.items?.[0]?.id || "";
        workspaceIdRef.current = first;
        setWorkspaceId(first);
        if (first) await loadWorkspaceData(first, session.csrf_token);
        const sessionList = await api<{ items: AuthSession[] }>("/api/v1/auth/sessions", session.csrf_token);
        if (!cancelled) setAuthSessions(sessionList.items || []);
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "";
          if (message.toLowerCase().includes("session") || message.toLowerCase().includes("sign in")) router.replace("/login");
          else setError(message || "Could not load your workspace.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; loadSequenceRef.current += 1; };
  }, [loadWorkspaceData, router]);

  function beginWhatsAppInboxOperation() {
    const epoch = whatsappBusyEpochRef.current;
    whatsappBusyCountRef.current += 1;
    setWhatsappInboxBusy(true);
    return epoch;
  }

  function endWhatsAppInboxOperation(epoch: number) {
    if (epoch !== whatsappBusyEpochRef.current) return;
    whatsappBusyCountRef.current = Math.max(0, whatsappBusyCountRef.current - 1);
    if (whatsappBusyCountRef.current === 0) {
      whatsappBusyEpochRef.current += 1;
      setWhatsappInboxBusy(false);
    }
  }

  function resetWhatsAppInboxOperations() {
    whatsappBusyEpochRef.current += 1;
    whatsappBusyCountRef.current = 0;
    setWhatsappInboxBusy(false);
  }

  function resetWorkspaceScopedState() {
    loadSequenceRef.current += 1;
    replyDetailSequenceRef.current += 1;
    replyDraftSequenceRef.current += 1;
    whatsappDetailSequenceRef.current += 1;
    whatsappConversationUpdateSequenceRef.current += 1;
    whatsappBulkUpdateSequenceRef.current += 1;
    whatsappInternalNoteSequenceRef.current += 1;
    whatsappMediaSequenceRef.current += 1;
    whatsappInboxQuerySequenceRef.current += 1;
    whatsappSavedViewsSequenceRef.current += 1;
    whatsappSLAActionSequenceRef.current += 1;
    whatsappSLALoadSequenceRef.current += 1;
    crmLoadSequenceRef.current += 1;
    setProspects([]); setProspectSearch(""); setProspectStageFilter("all"); setCrmOffset(0); setCrmTotal(0);
    setResearchQuery(""); setResearchResults([]); setResearchBusy(false);
    setDomainName(""); setDomainChallenge(null); setDomainBusy(false);
    setAuditUrl(""); setAuditReport(null); setAuditHistory([]); setAuditBusy(false); setGrowthReviewResult(null);
    setCampaigns([]); setCampaignName(""); setBusinessName(""); setOffer(""); setTargetProfile("");
    setSelectedCampaign(""); setSelectedProspect(""); setDraftChannel("email"); setDraftCallToAction(""); setDeliveryScheduleLocal("");
    setFollowupSequences([]); setFollowupEnrollments({}); setFollowupName(""); setFollowupCampaignId(""); setFollowupChannel("email");
    setFollowupProspectId(""); setFollowupResolutionReason({}); setFollowupResolutionEvidence({});
    setDrafts([]); setDraftEvents({}); setDraftHistoryOpen({}); setDeliveries([]);
    setCounts({}); setCampaignPerformance([]); setCampaignPerformanceUnavailable(false);
    setGrowthSchedules([]); setGrowthSchedulesUnavailable(false); setGrowthJobs([]); setGrowthJobsUnavailable(false); setGrowthJobReport(null);
    setScheduleStartUrl(""); setScheduleBusinessType(""); setScheduleTargetMarket(""); setScheduleQueries("");
    setEntitlements([]); setEntitlementsUnavailable(false); setIntegrationStatus(null);
    setProjects([]); setProjectName(""); setProjectWebsite(""); setProjectBusinessModel(""); setProjectMarket("");
    setProjectLanguage(""); setProjectAudience(""); setProjectOffer(""); setProjectGoal(""); setProjectBrandVoice(""); setProjectCompetitors("");
    setMembers([]); setInvitations([]); setInviteEmail(""); setInviteRole("member");
    setEmailAccounts([]); setSelectedEmailAccountId(""); setEditingEmailAccountId(null); setEmailAccountLabel("");
    setSmtpHost("smtp.gmail.com"); setSmtpUsername(""); setSmtpPassword(""); setSmtpFromEmail(""); setSmtpFromName("Outreach Marketing Agent");
    setWhatsappAccounts([]); setWhatsappTemplates({}); setWhatsappConversations([]); setWhatsappMessages([]);
    whatsappDeadLetterLoadSequenceRef.current += 1; whatsappDeadLetterLoadLockRef.current = false;
    setWhatsappNotes([]); setWhatsappActivity([]); setWhatsappDeadLetterEvents([]); setWhatsappDeadLetterOffset(25); setWhatsappDeadLetterHasMore(false); setWhatsappDeadLetterLoadingMore(false); setWhatsappSavedViews([]);
    setWhatsappFilterStatus(""); setWhatsappFilterPriority(""); setWhatsappFilterSearch(""); setWhatsappFilterAssignee("all");
    setWhatsappSelectedSavedView(""); setWhatsappSavedViewName(""); setWhatsappSavedViewsUnavailable(false); setWhatsappSLAUnavailable(false); setWhatsappSLAWarningMinutes(15); setWhatsappSLABreachMinutes(60);
    setWhatsappSLAPauseReason(""); setWhatsappSLASummary({ overdue: 0, at_risk: 0, within_sla: 0, paused: 0 });
    setSelectedWhatsAppBulkIds([]); setWhatsappBulkAssignee("__unchanged__"); setWhatsappBulkStatus(""); setWhatsappBulkPriority("");
    setWhatsappNoteDraft(""); setSelectedWhatsAppConversation(""); setWhatsappLabel(""); setWhatsappWabaId(""); setWhatsappPhoneNumberId(""); setWhatsappAccessToken("");
    setUnifiedReplyThreads([]); setSelectedReplyProspectId(""); setUnifiedReplyMessages([]); setUnifiedReplyBusy(false);
    setReplyDraftBody(""); setReplyDraftSubject(""); resetWhatsAppInboxOperations();
    setProspectName(""); setProspectCompany(""); setProspectEmail(""); setProspectPhone(""); setProspectWebsite(""); setEvidenceUrl(""); setFitReason("");
    setWordPressProjectId(""); setWordPressConnection(null); setWordPressEditing(false);
    setError(""); setNotice(""); setBusy(false); setIntegrationBusy(false); setRefreshing(false);
  }

  async function changeMemberRole(member: WorkspaceMember, role: string) {
    if (!workspaceId || !csrf || role === member.role) return;
    const requestedWorkspaceId = workspaceId;
    if (!window.confirm("Change " + member.email + "'s role to " + role + "?")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/workspaces/members/" + encodeURIComponent(member.user_id), csrf, {
        method: "PATCH", body: JSON.stringify({ workspace_id: requestedWorkspaceId, role }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Workspace member role updated.");
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (!requestedWorkspaceId || requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Member role could not be changed.");
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
    } finally { if (!requestedWorkspaceId || requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function removeMember(member: WorkspaceMember) {
    if (!workspaceId || !csrf || !window.confirm("Remove " + member.email + " from this workspace? Their account will remain active.")) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/workspaces/members/" + encodeURIComponent(member.user_id) + "?workspace_id=" + encodeURIComponent(requestedWorkspaceId), csrf, { method: "DELETE" });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Member removed from this workspace.");
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (!requestedWorkspaceId || requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Workspace member could not be removed.");
    } finally { if (!requestedWorkspaceId || requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function transferOwnership(member: WorkspaceMember) {
    if (!workspaceId || !csrf || workspaces.find(w => w.id === workspaceId)?.role !== "owner") return;
    const requestedWorkspaceId = workspaceId;
    if (!window.confirm("Transfer ownership of this workspace to " + member.email + "? You will become an admin and the new owner will control billing and workspace administration.")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/workspaces/" + encodeURIComponent(requestedWorkspaceId) + "/transfer-ownership", csrf, {
        method: "POST", body: JSON.stringify({ target_user_id: member.user_id }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setWorkspaces(current => current.map(workspace => workspace.id === requestedWorkspaceId ? { ...workspace, role: "admin" } : workspace));
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Workspace ownership transferred. Your role is now admin.");
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (!requestedWorkspaceId || requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Workspace ownership could not be transferred.");
    } finally { if (!requestedWorkspaceId || requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function loadAuthSessions() {
    if (!csrf) return;
    const requestedSequence = ++authSessionsSequenceRef.current;
    try {
      const result = await api<{ items: AuthSession[] }>("/api/v1/auth/sessions", csrf);
      if (requestedSequence !== authSessionsSequenceRef.current) return;
      setAuthSessions(result.items || []);
    } catch (err) {
      if (requestedSequence === authSessionsSequenceRef.current) setError(err instanceof Error ? err.message : "Signed-in sessions could not be loaded.");
    }
  }

  async function revokeAuthSession(session: AuthSession) {
    if (!csrf || session.is_current || !window.confirm("Sign out this device/session? It will need to sign in again.")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/auth/sessions/" + encodeURIComponent(session.id), csrf, { method: "DELETE" });
      setAuthSessions(current => current.filter(item => item.id !== session.id));
      setNotice("Selected session signed out.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Session could not be revoked.");
    } finally { setBusy(false); }
  }

  async function revokeOtherAuthSessions() {
    if (!csrf || !window.confirm("Sign out all other devices? This device will stay signed in.")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<{ revoked_count: number; current_session_preserved: boolean }>("/api/v1/auth/sessions/revoke-others", csrf, { method: "POST" });
      setAuthSessions(current => current.filter(item => item.is_current));
      setNotice(`Signed out ${result.revoked_count} other session${result.revoked_count === 1 ? "" : "s"}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Other sessions could not be revoked.");
    } finally { setBusy(false); }
  }

  async function createWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!csrf || !newWorkspaceName.trim()) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const created = await api<{ workspace_id: string; name: string; role: string }>("/api/v1/workspaces", csrf, {
        method: "POST", body: JSON.stringify({ name: newWorkspaceName.trim() }),
      });
      const switchSequence = ++workspaceSwitchSequenceRef.current;
      resetWorkspaceScopedState();
      setWorkspaces(current => [...current, { id: created.workspace_id, name: created.name, role: created.role }]);
      workspaceIdRef.current = created.workspace_id;
      setWorkspaceId(created.workspace_id);
      setWorkspaceName(created.name);
      setNewWorkspaceName("");
      setLoading(true);
      setNotice("Workspace created. You are its owner.");
      try {
        await refresh(created.workspace_id, csrf);
      } finally {
        if (workspaceSwitchSequenceRef.current === switchSequence) setLoading(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Workspace could not be created.");
    } finally { setBusy(false); }
  }

  async function downloadAccountExport() {
    if (!csrf) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<Record<string, unknown>>("/api/v1/account/export", csrf);
      const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json;charset=utf-8" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "outreach-marketing-agent-account-export.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setNotice("Your account data export has been prepared and downloaded.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Account export could not be prepared.");
    } finally { setBusy(false); }
  }

  async function deleteAccount() {
    if (!csrf || !window.confirm("Permanently deactivate this account, revoke all sessions, and pseudonymize its identity? Sole-member owned workspaces and their data will also be deleted. This cannot be undone.")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/account", csrf, { method: "DELETE" });
      router.replace("/login?account_deleted=1");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Account deletion could not be completed.");
      setBusy(false);
    }
  }

  async function saveWorkspaceName(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<{ workspace_id: string; name: string }>("/api/v1/workspaces/settings", csrf, {
        method: "PATCH", body: JSON.stringify({ workspace_id: requestedWorkspaceId, name: workspaceName }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setWorkspaceName(result.name);
      if (requestedWorkspaceId !== workspaceId) return;
      setWorkspaces(current => current.map(workspace => workspace.id === requestedWorkspaceId ? { ...workspace, name: result.name } : workspace));
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Workspace name updated.");
    } catch (err) {
      if (!requestedWorkspaceId || requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Workspace settings could not be saved.");
    } finally { if (!requestedWorkspaceId || requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function createEmailAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/integrations/email-accounts", csrf, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: requestedWorkspaceId, label: emailAccountLabel, smtp_host: smtpHost,
          smtp_port: 587, smtp_username: smtpUsername, smtp_password: smtpPassword,
          from_email: smtpFromEmail, from_name: smtpFromName, starttls: true,
        }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setEmailAccountLabel(""); setSmtpUsername(""); setSmtpPassword(""); setSmtpFromEmail("");
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Email account credentials encrypted and stored. Test the connection before queueing messages.");
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (!requestedWorkspaceId || requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Email account could not be connected.");
    } finally { if (!requestedWorkspaceId || requestedWorkspaceId === workspaceId) setBusy(false); }
  }


  async function saveEmailAccountChanges(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf || !editingEmailAccountId) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/integrations/email-accounts/" + encodeURIComponent(editingEmailAccountId), csrf, {
        method: "PUT",
        body: JSON.stringify({ workspace_id: requestedWorkspaceId, label: emailAccountLabel, smtp_host: smtpHost,
          smtp_port: 587, smtp_username: smtpUsername, smtp_password: smtpPassword,
          from_email: smtpFromEmail, from_name: smtpFromName, starttls: true }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setEditingEmailAccountId(null);
      setEmailAccountLabel(""); setSmtpUsername(""); setSmtpPassword(""); setSmtpFromEmail("");
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("SMTP credentials updated. Queued messages tied to the old sender were retired; retest this account before creating new deliveries.");
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (!requestedWorkspaceId || requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Email account could not be updated.");
    } finally { if (!requestedWorkspaceId || requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  function beginEmailAccountEdit(account: EmailAccount) {
    setEditingEmailAccountId(account.id);
    setEmailAccountLabel(account.label); setSmtpHost(account.smtp_host);
    setSmtpUsername(account.smtp_username); setSmtpPassword("");
    setSmtpFromEmail(account.from_email); setSmtpFromName(account.from_name);
    setError(""); setNotice("Enter the replacement SMTP password. Existing passwords are never displayed.");
  }

  async function testEmailAccount(account: EmailAccount) {
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<{ message: string }>("/api/v1/integrations/email-accounts/" + encodeURIComponent(account.id) + "/test?workspace_id=" + encodeURIComponent(requestedWorkspaceId), csrf, { method: "POST" });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice(result.message || "Email account connection test succeeded. No email was sent.");
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (!requestedWorkspaceId || requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Email account connection test failed.");
    } finally { if (!requestedWorkspaceId || requestedWorkspaceId === workspaceId) setBusy(false); }
  }


  async function sendEmailAccountTest(account: EmailAccount) {
    if (!workspaceId || !csrf || !window.confirm("Send one diagnostic email to " + account.from_email + "? This sends a real email and does not guarantee inbox placement.")) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<{ sent_to: string; note: string }>(
        "/api/v1/integrations/email-accounts/" + encodeURIComponent(account.id) + "/send-test",
        csrf,
        { method: "POST", body: JSON.stringify({ workspace_id: requestedWorkspaceId, confirm_send: true }) },
      );
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Diagnostic email submitted to " + result.sent_to + ". " + result.note);
    } catch (err) {
      if (!requestedWorkspaceId || requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Diagnostic email could not be submitted.");
    } finally { if (!requestedWorkspaceId || requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function openUnifiedReplyThread(thread: UnifiedReplyThread) {
    if (!workspaceId || !csrf) return;
    const requestSequence = ++replyDetailSequenceRef.current;
    const requestedWorkspaceId = workspaceId;
    setUnifiedReplyBusy(true); setError("");
    try {
      const result = await api<{ items: UnifiedReplyMessage[] }>(
        "/api/v1/prospects/" + encodeURIComponent(thread.prospect_id) + "/messages?workspace_id=" + encodeURIComponent(workspaceId) + "&limit=100",
        csrf,
      );
      if (requestSequence !== replyDetailSequenceRef.current || requestedWorkspaceId !== workspaceId) return;
      setSelectedReplyProspectId(thread.prospect_id);
      setUnifiedReplyMessages((result.items || []).slice().reverse());
    } catch (err) {
      if (requestSequence === replyDetailSequenceRef.current && requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Reply conversation could not be loaded.");
    } finally { if (requestSequence === replyDetailSequenceRef.current) setUnifiedReplyBusy(false); }
  }

  async function createUnifiedReplyDraft() {
    if (!workspaceId || !csrf || !selectedReplyProspectId) return;
    const thread = unifiedReplyThreads.find(item => item.prospect_id === selectedReplyProspectId);
    if (!thread || !replyDraftBody.trim()) return;
    const requestedWorkspaceId = workspaceId;
    const requestedSequence = ++replyDraftSequenceRef.current;
    setUnifiedReplyBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/prospects/" + encodeURIComponent(selectedReplyProspectId) + "/reply-drafts", csrf, {
        method: "POST", body: JSON.stringify({ workspace_id: requestedWorkspaceId, channel: thread.channel,
          subject: thread.channel === "email" ? replyDraftSubject.trim() : null, body: replyDraftBody.trim() }),
      });
      if (requestedSequence !== replyDraftSequenceRef.current || requestedWorkspaceId !== workspaceId) return;
      setReplyDraftBody(""); setReplyDraftSubject("");
      setNotice("Reply draft created and sent to the approval queue. No message was sent.");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedSequence === replyDraftSequenceRef.current && requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Reply draft could not be created.");
    } finally { if (requestedSequence === replyDraftSequenceRef.current) setUnifiedReplyBusy(false); }
  }

  async function deleteWhatsAppMedia(message: WhatsAppMessage) {
    if (!workspaceId || !csrf || !window.confirm("Permanently delete the stored WhatsApp attachment? The message record and provider metadata will remain.")) return;
    const requestedWorkspaceId = workspaceId;
    const requestedSequence = ++whatsappMediaSequenceRef.current;
    const busyEpoch = beginWhatsAppInboxOperation();; setError(""); setNotice("");
    try {
      await api("/api/v1/integrations/whatsapp/inbox/messages/" + encodeURIComponent(message.id) +
        "/media?workspace_id=" + encodeURIComponent(requestedWorkspaceId), csrf, { method: "DELETE" });
      if (requestedSequence !== whatsappMediaSequenceRef.current || requestedWorkspaceId !== workspaceId) return;
      setWhatsappMessages(items => items.map(item => item.id === message.id
        ? { ...item, media_downloaded_at: null, media_mime_type: null, media_filename: null, media_size: null }
        : item));
      setNotice("Stored WhatsApp attachment permanently deleted.");
    } catch (err) {
      if (requestedSequence === whatsappMediaSequenceRef.current && requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "WhatsApp attachment could not be deleted.");
    } finally { endWhatsAppInboxOperation(busyEpoch); }
  }

  async function downloadWhatsAppMedia(message: WhatsAppMessage) {
    if (!workspaceId || !csrf || !selectedWhatsAppConversation) return;
    const conversation = whatsappConversations.find(item => item.id === selectedWhatsAppConversation);
    if (!conversation) return;
    const requestedWorkspaceId = workspaceId;
    const requestedSequence = ++whatsappMediaSequenceRef.current;
    const busyEpoch = beginWhatsAppInboxOperation();; setError(""); setNotice("");
    try {
      const result = await api<{ size: number; filename?: string; already_downloaded?: boolean }>(
        "/api/v1/integrations/whatsapp/inbox/messages/" + encodeURIComponent(message.id) +
        "/media/download?workspace_id=" + encodeURIComponent(requestedWorkspaceId) +
        "&account_id=" + encodeURIComponent(conversation.account_id),
        csrf,
        { method: "POST" },
      );
      if (requestedSequence !== whatsappMediaSequenceRef.current || requestedWorkspaceId !== workspaceId) return;
      setNotice("WhatsApp attachment stored securely (" + (result.size || 0) + " bytes). Use the download link in the message.");
    } catch (err) {
      if (requestedSequence === whatsappMediaSequenceRef.current && requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "WhatsApp attachment could not be downloaded.");
    } finally { endWhatsAppInboxOperation(busyEpoch); }
  }

  async function updateWhatsAppConversation(conversation: WhatsAppConversation, patch: Partial<Pick<WhatsAppConversation, "assigned_to_user_id" | "inbox_status" | "priority">>) {
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    const requestedSequence = ++whatsappConversationUpdateSequenceRef.current;
    const busyEpoch = beginWhatsAppInboxOperation();; setError(""); setNotice("");
    try {
      const updated = await api<WhatsAppConversation>(
        "/api/v1/integrations/whatsapp/inbox/conversations/" + encodeURIComponent(conversation.id) +
        "?workspace_id=" + encodeURIComponent(requestedWorkspaceId), csrf,
        { method: "PATCH", body: JSON.stringify(patch) },
      );
      if (requestedSequence !== whatsappConversationUpdateSequenceRef.current || requestedWorkspaceId !== workspaceId) return;
      setWhatsappConversations(items => items.map(item => item.id === conversation.id ? { ...item, ...updated } : item));
      setNotice("WhatsApp conversation updated.");
    } catch (err) { if (requestedSequence === whatsappConversationUpdateSequenceRef.current && requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Conversation update failed."); }
    finally { endWhatsAppInboxOperation(busyEpoch); }
  }

  async function loadWhatsAppSavedViews(selectedWorkspaceId = workspaceId, token = csrf) {
    if (!selectedWorkspaceId || !token) return;
    const requestedWorkspaceId = selectedWorkspaceId;
    const requestedSequence = ++whatsappSavedViewsSequenceRef.current;
    try {
      const result = await api<{ items: WhatsAppSavedView[] }>(
        "/api/v1/integrations/whatsapp/inbox/saved-views?workspace_id=" + encodeURIComponent(requestedWorkspaceId), token,
      );
      if (requestedSequence !== whatsappSavedViewsSequenceRef.current || requestedWorkspaceId !== workspaceIdRef.current) return;
      setWhatsappSavedViews(result.items || []);
      setWhatsappSavedViewsUnavailable(false);
    } catch (err) {
      if (requestedSequence === whatsappSavedViewsSequenceRef.current && requestedWorkspaceId === workspaceIdRef.current) {
        setWhatsappSavedViewsUnavailable(true);
        setError(err instanceof Error ? err.message : "Saved inbox views could not be loaded.");
      }
    }
  }

  async function saveWhatsAppCurrentView() {
    if (!workspaceId || !csrf || !whatsappSavedViewName.trim()) return;
    const requestedWorkspaceId = workspaceId;
    const requestedSequence = ++whatsappSavedViewsSequenceRef.current;
    const filters: WhatsAppSavedView["filters"] = {};
    if (whatsappFilterStatus) filters.inbox_status = whatsappFilterStatus;
    if (whatsappFilterPriority) filters.priority = whatsappFilterPriority;
    if (whatsappFilterSearch.trim()) filters.search = whatsappFilterSearch.trim();
    if (whatsappFilterAssignee === "me") filters.assigned_to_me = true;
    else if (whatsappFilterAssignee === "unassigned") filters.unassigned = true;
    else if (whatsappFilterAssignee.startsWith("user:")) filters.assigned_to_user_id = whatsappFilterAssignee.slice(5);
    const busyEpoch = beginWhatsAppInboxOperation();; setError("");
    try {
      const saved = await api<WhatsAppSavedView>(
        "/api/v1/integrations/whatsapp/inbox/saved-views?workspace_id=" + encodeURIComponent(requestedWorkspaceId),
        csrf, { method: "POST", body: JSON.stringify({ name: whatsappSavedViewName.trim(), filters }) },
      );
      if (requestedSequence !== whatsappSavedViewsSequenceRef.current || requestedWorkspaceId !== workspaceId) return;
      setWhatsappSavedViews(items => [...items.filter(item => item.id !== saved.id && item.name.toLowerCase() !== saved.name.toLowerCase()), saved]);
      setWhatsappSelectedSavedView(saved.id); setWhatsappSavedViewName("");
      setNotice("Inbox view saved to your workspace account.");
    } catch (err) {
      if (requestedSequence === whatsappSavedViewsSequenceRef.current && requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Inbox view could not be saved.");
    } finally { endWhatsAppInboxOperation(busyEpoch); }
  }

  async function applyWhatsAppSavedView(viewId: string) {
    const view = whatsappSavedViews.find(item => item.id === viewId);
    if (!view || !workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    const requestedSequence = ++whatsappInboxQuerySequenceRef.current;
    const requestedDetailSequence = whatsappDetailSequenceRef.current;
    setWhatsappSelectedSavedView(viewId);
    setWhatsappFilterStatus(view.filters.inbox_status || "");
    setWhatsappFilterPriority(view.filters.priority || "");
    setWhatsappFilterSearch(view.filters.search || "");
    setWhatsappFilterAssignee(view.filters.assigned_to_me ? "me" : view.filters.unassigned ? "unassigned" : view.filters.assigned_to_user_id ? "user:"+view.filters.assigned_to_user_id : "all");
    const params = new URLSearchParams({ workspace_id: requestedWorkspaceId, limit: "50" });
    if (view.filters.inbox_status) params.set("inbox_status", view.filters.inbox_status);
    if (view.filters.priority) params.set("priority", view.filters.priority);
    if (view.filters.search) params.set("search", view.filters.search);
    if (view.filters.assigned_to_me) params.set("assigned_to_me", "true");
    if (view.filters.unassigned) params.set("unassigned", "true");
    if (view.filters.assigned_to_user_id) params.set("assigned_to_user_id", view.filters.assigned_to_user_id);
    const busyEpoch = beginWhatsAppInboxOperation();;
    try {
      const result = await api<{ items: WhatsAppConversation[] }>("/api/v1/integrations/whatsapp/inbox/conversations?"+params.toString(),csrf);
      if (requestedSequence !== whatsappInboxQuerySequenceRef.current || requestedWorkspaceId !== workspaceId) return;
      const nextConversations = result.items || [];
      setWhatsappConversations(nextConversations);
      if (requestedDetailSequence === whatsappDetailSequenceRef.current && selectedWhatsAppConversation && !nextConversations.some(item => item.id === selectedWhatsAppConversation)) {
        whatsappDetailSequenceRef.current += 1;
        whatsappInternalNoteSequenceRef.current += 1;
        setSelectedWhatsAppConversation("");
        setWhatsappMessages([]);
        setWhatsappNotes([]);
        setWhatsappActivity([]);
        setWhatsappNoteDraft("");
      }
      await loadWhatsAppSLA();
      if (requestedSequence !== whatsappInboxQuerySequenceRef.current || requestedWorkspaceId !== workspaceId) return;
      setSelectedWhatsAppBulkIds([]);
    } catch (err) {
      if (requestedSequence === whatsappInboxQuerySequenceRef.current && requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Saved inbox view could not be applied.");
    } finally { endWhatsAppInboxOperation(busyEpoch); }
  }

  async function deleteWhatsAppSavedView(viewId: string) {
    if (!workspaceId || !csrf || !window.confirm("Delete this saved inbox view?")) return;
    const requestedWorkspaceId = workspaceId;
    const requestedSequence = ++whatsappSavedViewsSequenceRef.current;
    const busyEpoch = beginWhatsAppInboxOperation();; setError("");
    try {
      await api<{ deleted: boolean }>(
        "/api/v1/integrations/whatsapp/inbox/saved-views/"+encodeURIComponent(viewId)+"?workspace_id="+encodeURIComponent(requestedWorkspaceId),
        csrf,{method:"DELETE"},
      );
      if (requestedSequence !== whatsappSavedViewsSequenceRef.current || requestedWorkspaceId !== workspaceId) return;
      setWhatsappSavedViews(items=>items.filter(item=>item.id!==viewId));
      if (whatsappSelectedSavedView===viewId) setWhatsappSelectedSavedView("");
    } catch (err) {
      if (requestedSequence === whatsappSavedViewsSequenceRef.current && requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Saved view could not be deleted.");
    } finally { endWhatsAppInboxOperation(busyEpoch); }
  }

  async function applyWhatsAppBulkUpdate() {
    if (!workspaceId || !csrf || !selectedWhatsAppBulkIds.length) return;
    const requestedWorkspaceId = workspaceId;
    const requestedSequence = ++whatsappBulkUpdateSequenceRef.current;
    const patch: Record<string, string | null> = {};
    if (whatsappBulkAssignee !== "__unchanged__") patch.assigned_to_user_id = whatsappBulkAssignee || null;
    if (whatsappBulkStatus) patch.inbox_status = whatsappBulkStatus;
    if (whatsappBulkPriority) patch.priority = whatsappBulkPriority;
    if (!Object.keys(patch).length) { setError("Choose at least one bulk action."); return; }
    const busyEpoch = beginWhatsAppInboxOperation();; setError(""); setNotice("");
    try {
      const result = await api<{ updated_count: number; items: WhatsAppConversation[] }>(
        "/api/v1/integrations/whatsapp/inbox/conversations/bulk-update?workspace_id=" + encodeURIComponent(requestedWorkspaceId),
        csrf, { method: "POST", body: JSON.stringify({ conversation_ids: selectedWhatsAppBulkIds, ...patch }) },
      );
      if (requestedSequence !== whatsappBulkUpdateSequenceRef.current || requestedWorkspaceId !== workspaceId) return;
      const byId = new Map(result.items.map(item => [item.id, item]));
      setWhatsappConversations(items => items.map(item => byId.has(item.id) ? { ...item, ...byId.get(item.id)! } : item));
      setSelectedWhatsAppBulkIds([]);
      setWhatsappBulkAssignee("__unchanged__"); setWhatsappBulkStatus(""); setWhatsappBulkPriority("");
      setNotice(result.updated_count + " WhatsApp conversations updated.");
    } catch (err) {
      if (requestedSequence === whatsappBulkUpdateSequenceRef.current && requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Bulk conversation update failed.");
    } finally { endWhatsAppInboxOperation(busyEpoch); }
  }

  async function addWhatsAppInternalNote() {
    if (!workspaceId || !csrf || !selectedWhatsAppConversation || !whatsappNoteDraft.trim()) return;
    const requestedWorkspaceId = workspaceId;
    const requestedConversationId = selectedWhatsAppConversation;
    const requestedSequence = ++whatsappInternalNoteSequenceRef.current;
    const busyEpoch = beginWhatsAppInboxOperation();; setError(""); setNotice("");
    try {
      const note = await api<WhatsAppInternalNote>(
        "/api/v1/integrations/whatsapp/inbox/conversations/" + encodeURIComponent(requestedConversationId) +
        "/notes?workspace_id=" + encodeURIComponent(requestedWorkspaceId), csrf,
        { method: "POST", body: JSON.stringify({ body: whatsappNoteDraft.trim() }) },
      );
      if (requestedSequence !== whatsappInternalNoteSequenceRef.current || requestedWorkspaceId !== workspaceId || requestedConversationId !== selectedWhatsAppConversation) return;
      setWhatsappNotes(items => [...items, note]); setWhatsappNoteDraft("");
      setNotice("Internal note added. It was not sent to the WhatsApp contact.");
    } catch (err) {
      if (requestedSequence === whatsappInternalNoteSequenceRef.current && requestedWorkspaceId === workspaceId && requestedConversationId === selectedWhatsAppConversation) setError(err instanceof Error ? err.message : "Internal note could not be saved.");
    } finally { endWhatsAppInboxOperation(busyEpoch); }
  }

  async function openWhatsAppConversation(conversation: WhatsAppConversation) {
    if (!workspaceId || !csrf) return;
    const requestSequence = ++whatsappDetailSequenceRef.current;
    // A pending note write belongs to the previous thread; invalidate it before
    // switching the selected conversation and its detail panels.
    whatsappInternalNoteSequenceRef.current += 1;
    const requestedWorkspaceId = workspaceId;
    const requestedCsrf = csrf;
    // Switch the visible conversation immediately so the previous contact's
    // messages and notes are never shown while the next conversation loads.
    setSelectedWhatsAppConversation(conversation.id);
    setWhatsappMessages([]);
    setWhatsappNotes([]);
    setWhatsappActivity([]);
    setWhatsappNoteDraft("");
    const busyEpoch = beginWhatsAppInboxOperation();;
    setError("");
    try {
      const conversationPath = "/api/v1/integrations/whatsapp/inbox/conversations/" + encodeURIComponent(conversation.id);
      const [result, notes, activity] = await Promise.all([
        api<{ items: WhatsAppMessage[] }>(conversationPath + "/messages?workspace_id=" + encodeURIComponent(requestedWorkspaceId) + "&limit=100", requestedCsrf),
        api<{ items: WhatsAppInternalNote[] }>(conversationPath + "/notes?workspace_id=" + encodeURIComponent(requestedWorkspaceId) + "&limit=50", requestedCsrf),
        api<{ items: WhatsAppActivity[] }>(conversationPath + "/activity?workspace_id=" + encodeURIComponent(requestedWorkspaceId) + "&limit=50", requestedCsrf),
      ]);
      if (requestSequence !== whatsappDetailSequenceRef.current || requestedWorkspaceId !== workspaceId) return;
      // Commit the detail panels together so messages, notes and activity always
      // belong to the same conversation snapshot.
      setWhatsappMessages((result.items || []).slice().reverse());
      setWhatsappNotes((notes.items || []).slice().reverse());
      setWhatsappActivity((activity.items || []).slice().reverse());
    } catch (err) {
      if (requestSequence === whatsappDetailSequenceRef.current && requestedWorkspaceId === workspaceId) {
        setError(err instanceof Error ? err.message : "WhatsApp conversation could not be loaded.");
      }
    } finally {
      endWhatsAppInboxOperation(busyEpoch);
    }
  }

  async function createWhatsAppAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    const requestedCsrf = csrf;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/integrations/whatsapp/accounts", requestedCsrf, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: requestedWorkspaceId, label: whatsappLabel, waba_id: whatsappWabaId,
          phone_number_id: whatsappPhoneNumberId, access_token: whatsappAccessToken,
        }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setWhatsappLabel(""); setWhatsappWabaId(""); setWhatsappPhoneNumberId(""); setWhatsappAccessToken("");
      setNotice("Meta account credentials encrypted and saved as pending verification.");
      await refresh(requestedWorkspaceId, requestedCsrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "WhatsApp account could not be saved.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function verifyWhatsAppAccount(account: WhatsAppAccount) {
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<{ verified: boolean; notice: string }>("/api/v1/integrations/whatsapp/accounts/" + encodeURIComponent(account.id) + "/verify?workspace_id=" + encodeURIComponent(requestedWorkspaceId), csrf, { method: "POST" });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice(result.notice || "Meta account and WABA webhook subscription verified. Outbound sending remains separately gated by server configuration and consent.");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "WhatsApp account verification failed.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function rotateWhatsAppToken(account: WhatsAppAccount) {
    if (!workspaceId || !csrf || !window.confirm("Replace the access token for " + account.label + "? Pending deliveries will be cancelled and must be queued again.")) return;
    const token = window.prompt("Paste the new Meta access token. It will be encrypted and will not be shown again.");
    if (!token?.trim()) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<{ status: string; queued_reservations_released: number }>(
        "/api/v1/integrations/whatsapp/accounts/" + encodeURIComponent(account.id) + "/rotate-token",
        csrf,
        { method: "POST", body: JSON.stringify({ workspace_id: requestedWorkspaceId, access_token: token.trim() }) },
      );
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("WhatsApp token rotated. " + result.queued_reservations_released + " queued reservation(s) released. Verify the account again.");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "WhatsApp token could not be rotated.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function syncWhatsAppTemplates(account: WhatsAppAccount) {
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<{ templates_received: number; templates_synced: number; templates_skipped: number; sending_enabled: boolean }>(
        "/api/v1/integrations/whatsapp/accounts/" + encodeURIComponent(account.id) + "/templates/sync?workspace_id=" + encodeURIComponent(requestedWorkspaceId),
        csrf,
        { method: "POST" },
      );
      if (requestedWorkspaceId !== workspaceId) return;
      const refreshed = await api<{ items: WhatsAppTemplate[] }>(
        "/api/v1/integrations/whatsapp/accounts/" + encodeURIComponent(account.id) + "/templates?workspace_id=" + encodeURIComponent(requestedWorkspaceId),
        csrf,
      );
      if (requestedWorkspaceId !== workspaceId) return;
      setWhatsappTemplates(current => ({ ...current, [account.id]: refreshed.items || [] }));
      setNotice("Meta template sync complete for " + account.label + ": " + result.templates_synced + " saved, " + result.templates_skipped + " skipped from " + result.templates_received + " received. Queue dispatch is controlled by the server-side WhatsApp feature flag.");
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "WhatsApp templates could not be synchronized.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function disableWhatsAppAccount(account: WhatsAppAccount) {
    if (!workspaceId || !csrf || !window.confirm("Disable the WhatsApp account " + account.label + "?")) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/integrations/whatsapp/accounts/" + encodeURIComponent(account.id) + "?workspace_id=" + encodeURIComponent(requestedWorkspaceId), csrf, { method: "DELETE" });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("WhatsApp account disabled.");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "WhatsApp account could not be disabled.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function disableEmailAccount(account: EmailAccount) {
    if (!workspaceId || !csrf || !window.confirm("Disable " + account.label + "? New queue requests cannot use this account.")) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/integrations/email-accounts/" + encodeURIComponent(account.id) + "?workspace_id=" + encodeURIComponent(requestedWorkspaceId), csrf, { method: "DELETE" });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Email account disabled. Its queued messages were retired and will not be sent later if the account is re-enabled.");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Email account could not be disabled.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function createInvitation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/workspaces/invitations", csrf, {
        method: "POST",
        body: JSON.stringify({ workspace_id: requestedWorkspaceId, email: inviteEmail, role: inviteRole }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setInviteEmail("");
      setNotice("Invitation email sent. The recipient must sign in with that email address to accept.");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Workspace invitation could not be sent.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function revokeInvitation(invitation: Invitation) {
    if (!workspaceId || !csrf || !window.confirm("Revoke the pending invitation for " + invitation.invited_email + "?")) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/workspaces/invitations/" + encodeURIComponent(invitation.id) + "?workspace_id=" + encodeURIComponent(requestedWorkspaceId), csrf, { method: "DELETE" });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Pending invitation revoked.");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Invitation could not be revoked.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function updateProject(event: FormEvent<HTMLFormElement>, project: Project) {
    event.preventDefault();
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    const form = new FormData(event.currentTarget);
    const value = (key: string) => String(form.get(key) || "");
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/projects/" + encodeURIComponent(project.id), csrf, {
        method: "PATCH",
        body: JSON.stringify({
          workspace_id: requestedWorkspaceId,
          name: value("name"),
          website_url: value("website_url") || null,
          business_model: value("business_model"),
          target_market: value("target_market"),
          language: value("language"),
          audience: value("audience"),
          offer: value("offer"),
          conversion_goal: value("conversion_goal"),
          brand_voice: value("brand_voice"),
          competitors: value("competitors").split(String.fromCharCode(10)).map(item => item.trim()).filter(Boolean).slice(0, 20),
        }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Project settings updated.");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Project settings could not be updated.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function archiveProject(project: Project) {
    if (!workspaceId || !csrf || !["owner", "admin"].includes(workspaces.find(w => w.id === workspaceId)?.role || "")) return;
    if (!window.confirm("Archive project " + project.name + "? It will disappear from the active project list; existing workspace records are not deleted.")) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/projects/" + encodeURIComponent(project.id) + "?workspace_id=" + encodeURIComponent(requestedWorkspaceId), csrf, { method: "DELETE" });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Project archived. Its historical campaign and CRM records remain in the workspace.");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Project could not be archived.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      const competitors = projectCompetitors.split(String.fromCharCode(10)).map(item => item.trim()).filter(Boolean).slice(0, 20);
      await api("/api/v1/projects", csrf, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: requestedWorkspaceId, name: projectName, website_url: projectWebsite || null,
          business_model: projectBusinessModel, target_market: projectMarket, language: projectLanguage,
          audience: projectAudience, offer: projectOffer, conversion_goal: projectGoal,
          brand_voice: projectBrandVoice, competitors,
        }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setProjectName(""); setProjectWebsite(""); setProjectBusinessModel(""); setProjectMarket("");
      setProjectLanguage(""); setProjectAudience(""); setProjectOffer(""); setProjectGoal("");
      setProjectBrandVoice(""); setProjectCompetitors("");
      setNotice("Project profile saved. Website ownership verification is a separate step.");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Project could not be saved.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function updateCampaign(event: FormEvent<HTMLFormElement>, campaign: Campaign) {
    event.preventDefault();
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    const form = new FormData(event.currentTarget);
    const status = String(form.get("status") || "draft");
    if (status === "archived" && !window.confirm("Archive campaign " + campaign.name + "? New drafts and queued sends will be blocked; existing history is retained.")) return;
    const payload = {
      workspace_id: requestedWorkspaceId,
      name: String(form.get("name") || "").trim(),
      client_business: String(form.get("client_business") || "").trim(),
      client_offer: String(form.get("client_offer") || "").trim(),
      target_customer_profile: String(form.get("target_customer_profile") || "").trim(),
      status,
    };
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/campaigns/" + encodeURIComponent(campaign.id), csrf, { method: "PATCH", body: JSON.stringify(payload) });
      if (requestedWorkspaceId !== workspaceId) return;
      if (status === "archived") setSelectedCampaign(current => current === campaign.id ? "" : current);
      setNotice("Campaign settings saved.");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Campaign could not be updated.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function createCampaign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/campaigns", csrf, { method: "POST", body: JSON.stringify({
        workspace_id: requestedWorkspaceId, name: campaignName, client_business: businessName,
        client_offer: offer, target_customer_profile: targetProfile,
      }) });
      if (requestedWorkspaceId !== workspaceId) return;
      setCampaignName(""); setBusinessName(""); setOffer(""); setTargetProfile("");
      setNotice("Campaign created. No outreach has been sent.");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) { if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Campaign could not be created."); }
    finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function createFollowupSequence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf || !followupCampaignId) return;
    let steps: unknown;
    try { steps = JSON.parse(followupStepsJson); } catch { setError("Follow-up steps must be valid JSON."); return; }
    if (!Array.isArray(steps) || !steps.length || steps.length > 10) { setError("Provide between 1 and 10 follow-up steps."); return; }
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      const created = await api<FollowupSequence>("/api/v1/campaigns/" + encodeURIComponent(followupCampaignId) + "/follow-up-sequences", csrf, {
        method: "POST", body: JSON.stringify({ workspace_id: requestedWorkspaceId, name: followupName, channel: followupChannel, steps }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      await api("/api/v1/follow-up-sequences/" + encodeURIComponent(created.id), csrf, {
        method: "PATCH", body: JSON.stringify({ workspace_id: requestedWorkspaceId, status: "active" }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setFollowupName(""); setNotice("Follow-up sequence created and activated. Each due step creates a draft for human approval; nothing is sent automatically.");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) { if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Follow-up sequence could not be created."); }
    finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function enrollFollowup(sequence: FollowupSequence) {
    if (!workspaceId || !csrf || !followupProspectId) { setError("Choose a prospect before enrolling."); return; }
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/follow-up-sequences/" + encodeURIComponent(sequence.id) + "/enroll", csrf, {
        method: "POST", body: JSON.stringify({ workspace_id: requestedWorkspaceId, prospect_id: followupProspectId }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Prospect enrolled. The scheduler will create the next follow-up draft when its delay is due.");
      await loadFollowupEnrollments(sequence);
      if (requestedWorkspaceId !== workspaceId) return;
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) { if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Prospect could not be enrolled."); }
    finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function loadFollowupEnrollments(sequence: FollowupSequence) {
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    try {
      const result = await api<{ items: FollowupEnrollment[] }>("/api/v1/follow-up-sequences/" + encodeURIComponent(sequence.id) + "/enrollments?workspace_id=" + encodeURIComponent(requestedWorkspaceId), csrf);
      if (requestedWorkspaceId !== workspaceId) return;
      setFollowupEnrollments(current => ({ ...current, [sequence.id]: result.items || [] }));
    } catch (err) { if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Follow-up enrollments could not be loaded."); }
  }

  async function setFollowupStatus(sequence: FollowupSequence, status: string) {
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/follow-up-sequences/" + encodeURIComponent(sequence.id), csrf, {
        method: "PATCH", body: JSON.stringify({ workspace_id: requestedWorkspaceId, status }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Follow-up sequence " + status + ".");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) { if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Follow-up sequence could not be updated."); }
    finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function setFollowupEnrollmentStatus(sequence: FollowupSequence, enrollment: FollowupEnrollment, status: string) {
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/follow-up-enrollments/" + encodeURIComponent(enrollment.id), csrf, {
        method: "PATCH", body: JSON.stringify({ workspace_id: requestedWorkspaceId, status }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      await loadFollowupEnrollments(sequence);
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Follow-up enrollment " + status + ".");
    } catch (err) { if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Follow-up enrollment could not be updated."); }
    finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function resolveFollowupDelivery(sequence: FollowupSequence, enrollment: FollowupEnrollment, outcome: "delivered" | "not_delivered") {
    if (!workspaceId || !csrf || !enrollment.current_delivery_id) return;
    const reason = followupResolutionReason[enrollment.id] || "";
    const evidenceUrl = followupResolutionEvidence[enrollment.id] || "";
    if (reason.trim().length < 12 || !evidenceUrl.trim().startsWith("https://")) {
      setError("Enter a resolution reason (at least 12 characters) and an HTTPS evidence URL.");
      return;
    }
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/follow-up-enrollments/" + encodeURIComponent(enrollment.id) + "/resolve-delivery", csrf, {
        method: "POST",
        body: JSON.stringify({ workspace_id: requestedWorkspaceId, delivery_id: enrollment.current_delivery_id, outcome, reason: reason.trim(), evidence_url: evidenceUrl.trim() }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      await loadFollowupEnrollments(sequence);
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice(outcome === "delivered" ? "Provider-confirmed delivery recorded; the sequence advanced safely." : "Non-delivery recorded; the enrollment was stopped without retrying the old delivery.");
    } catch (err) { if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Follow-up delivery resolution could not be completed."); }
    finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function createDomainChallenge(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf || !domainName.trim()) return;
    const requestedWorkspaceId = workspaceId;
    setDomainBusy(true); setError(""); setNotice(""); setDomainChallenge(null);
    try {
      const result = await api<DomainChallenge>("/api/v1/domains/challenges", csrf, {
        method: "POST",
        body: JSON.stringify({ workspace_id: requestedWorkspaceId, domain: domainName.trim() }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setDomainChallenge(result);
      setNotice("DNS record created. Publish the record exactly as shown, then verify it.");
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Domain challenge could not be created.");
    } finally { if (requestedWorkspaceId === workspaceId) setDomainBusy(false); }
  }

  async function verifyDomain() {
    if (!workspaceId || !csrf || !domainChallenge) return;
    const requestedWorkspaceId = workspaceId;
    setDomainBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/domains/verify", csrf, {
        method: "POST",
        body: JSON.stringify({ workspace_id: requestedWorkspaceId, domain: domainChallenge.domain }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setAuditUrl("https://" + domainChallenge.domain + "/");
      setDomainChallenge(null);
      setNotice("Domain verified. Run a bounded read-only audit on the verified host.");
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Domain verification could not be completed.");
    } finally { if (requestedWorkspaceId === workspaceId) setDomainBusy(false); }
  }

  async function openSavedAudit(reportId: string) {
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    setAuditBusy(true); setError(""); setNotice("");
    try {
      const result = await api<{ report_id: string; workspace_id: string; start_url: string; status: string; created_at: string; report: WebsiteAudit["report"] & GrowthReviewReport }>("/api/v1/website-audits/" + encodeURIComponent(reportId) + "?workspace_id=" + encodeURIComponent(requestedWorkspaceId), csrf);
      if (requestedWorkspaceId !== workspaceId) return;
      if (result.report.report_type === "website_growth_review") {
        setAuditReport(null);
        setGrowthReviewResult({
          report_id: result.report_id,
          workspace_id: result.workspace_id,
          project_id: result.report.project_id || "",
          project_name: result.report.project_name || "Saved project",
          report: result.report,
          created_at: result.created_at,
          notice: "Saved growth review loaded for human review.",
        });
      } else {
        setGrowthReviewResult(null);
        setAuditReport(result as WebsiteAudit);
      }
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Saved website audit could not be opened.");
    } finally { if (requestedWorkspaceId === workspaceId) setAuditBusy(false); }
  }

  async function runWebsiteAudit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf || !auditUrl.trim()) return;
    const requestedWorkspaceId = workspaceId;
    setAuditBusy(true); setError(""); setNotice(""); setAuditReport(null);
    try {
      const result = await api<WebsiteAudit>("/api/v1/website-audits", csrf, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: requestedWorkspaceId,
          start_url: auditUrl.trim(),
          max_pages: 5,
          idempotency_key: "site-audit-" + crypto.randomUUID(),
        }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setAuditReport(result);
      setNotice(result.notice || "Read-only audit completed.");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Website audit could not be completed.");
    } finally { if (requestedWorkspaceId === workspaceId) setAuditBusy(false); }
  }

  async function searchProspects(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf || !researchQuery.trim()) return;
    const requestedWorkspaceId = workspaceId;
    setResearchBusy(true); setError(""); setNotice(""); setResearchResults([]);
    try {
      const result = await api<{ items: ResearchResult[]; notice?: string }>("/api/v1/research/prospects/search", csrf, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: requestedWorkspaceId,
          query: researchQuery.trim(),
          count: 10,
          idempotency_key: "research-" + crypto.randomUUID(),
        }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setResearchResults(result.items || []);
      setNotice(result.notice || "Research results loaded for human review.");
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Public-web research could not be completed.");
    } finally { if (requestedWorkspaceId === workspaceId) setResearchBusy(false); }
  }


  async function searchInfluencers(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf || !influencerQuery.trim() || influencerPlatforms.length === 0) return;
    const requestedWorkspaceId = workspaceId;
    setInfluencerBusy(true); setError(""); setNotice(""); setInfluencerResults([]);
    try {
      const result = await api<{ items: InfluencerCandidate[]; notice?: string }>(
        "/api/v1/research/influencers/search", csrf, {
          method: "POST",
          body: JSON.stringify({
            workspace_id: requestedWorkspaceId,
            query: influencerQuery.trim(),
            platforms: influencerPlatforms,
            count: 10,
            idempotency_key: "influencer-research-" + crypto.randomUUID(),
          }),
        }
      );
      if (requestedWorkspaceId !== workspaceId) return;
      setInfluencerResults(result.items || []);
      setNotice(result.notice || "Public creator-profile candidates are ready for review.");
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Influencer discovery could not be completed.");
    } finally {
      if (requestedWorkspaceId === workspaceId) setInfluencerBusy(false);
    }
  }

  async function updateContentBrief(event: FormEvent<HTMLFormElement>, item: ContentBrief) {
    event.preventDefault();
    if (!workspaceId || !csrf) return;
    const form = new FormData(event.currentTarget);
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/content-briefs/" + encodeURIComponent(item.id), csrf, {
        method: "PATCH",
        body: JSON.stringify({
          workspace_id: workspaceId,
          title: String(form.get("title") || ""),
          brief: String(form.get("brief") || ""),
          target_keyword: String(form.get("target_keyword") || ""),
          status: "in_review",
        }),
      });
      const result = await api<{ items: ContentBrief[] }>("/api/v1/content-briefs?workspace_id=" + encodeURIComponent(workspaceId), csrf);
      setContentBriefs(result.items || []);
      setNotice("Content brief submitted for admin review.");
    } catch (err) { setError(err instanceof Error ? err.message : "Content brief could not be updated."); }
    finally { setBusy(false); }
  }

  async function reviewContentBrief(item: ContentBrief, decision: "approved" | "rejected") {
    if (!workspaceId || !csrf) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/content-briefs/" + encodeURIComponent(item.id) + "/review", csrf, {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspaceId, decision }),
      });
      const result = await api<{ items: ContentBrief[] }>("/api/v1/content-briefs?workspace_id=" + encodeURIComponent(workspaceId), csrf);
      setContentBriefs(result.items || []);
      setNotice(decision === "approved" ? "Editorial brief approved. No publishing action was taken." : "Editorial brief returned for revision.");
    } catch (err) { setError(err instanceof Error ? err.message : "Editorial review could not be completed."); }
    finally { setBusy(false); }
  }

  async function createContentBrief(actionId: string) {
    if (!workspaceId || !csrf || !growthReviewResult) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const created = await api<ContentBrief>("/api/v1/content-briefs", csrf, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspaceId,
          project_id: growthReviewResult.project_id,
          report_id: growthReviewResult.report_id,
          action_id: actionId,
        }),
      });
      const result = await api<{ items: ContentBrief[] }>("/api/v1/content-briefs?workspace_id=" + encodeURIComponent(workspaceId), csrf);
      setContentBriefs(result.items || []);
      setNotice("Content brief saved to the editorial workflow. It is not published.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Content brief could not be created.");
    } finally { setBusy(false); }
  }

  async function generateContentArticle(item: ContentBrief) {
    if (!workspaceId || !csrf) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/content-briefs/" + encodeURIComponent(item.id) + "/generate-article?workspace_id=" + encodeURIComponent(workspaceId), csrf, { method: "POST" });
      const result = await api<{ items: ContentBrief[] }>("/api/v1/content-briefs?workspace_id=" + encodeURIComponent(workspaceId), csrf);
      setContentBriefs(result.items || []);
      setNotice("SEO article draft generated. It is editable and has not been published.");
    } catch (err) { setError(err instanceof Error ? err.message : "Article generation failed."); }
    finally { setBusy(false); }
  }

  async function updateContentArticle(event: FormEvent<HTMLFormElement>, item: ContentBrief) {
    event.preventDefault();
    if (!workspaceId || !csrf) return;
    const form = new FormData(event.currentTarget);
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/content-briefs/" + encodeURIComponent(item.id) + "/article", csrf, {
        method: "PATCH",
        body: JSON.stringify({
          workspace_id: workspaceId,
          article_title: String(form.get("article_title") || ""),
          meta_title: String(form.get("meta_title") || ""),
          meta_description: String(form.get("meta_description") || ""),
          article_body: String(form.get("article_body") || ""),
          status: "in_review",
        }),
      });
      const result = await api<{ items: ContentBrief[] }>("/api/v1/content-briefs?workspace_id=" + encodeURIComponent(workspaceId), csrf);
      setContentBriefs(result.items || []);
      setEditingArticleId(null);
      setNotice("Article draft submitted for editorial review. It remains unpublished.");
    } catch (err) { setError(err instanceof Error ? err.message : "Article draft could not be saved."); }
    finally { setBusy(false); }
  }

  async function saveWordPressConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf) return;
    const form = new FormData(event.currentTarget);
    setWordPressBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/integrations/wordpress/connection", csrf, {
        method: "PUT",
        body: JSON.stringify({ workspace_id: workspaceId, project_id: wordpressProjectId || null, site_url: String(form.get("site_url") || "").trim(), username: String(form.get("username") || "").trim(), application_password: String(form.get("application_password") || "").trim() }),
      });
      const result = await api<{connected:boolean;inherited_from_workspace?:boolean;connection?:{id:string;site_url:string;username:string;status:string;project_id?:string|null}}>("/api/v1/integrations/wordpress/connection?workspace_id="+encodeURIComponent(workspaceId)+(wordpressProjectId ? "&project_id="+encodeURIComponent(wordpressProjectId) : ""),csrf);
      setWordPressConnection(result);
      setWordPressEditing(false);
      setNotice("WordPress credentials encrypted and saved. Verify the connection before transferring articles.");
    } catch (err) { setError(err instanceof Error ? err.message : "WordPress connection could not be saved."); }
    finally { setWordPressBusy(false); }
  }

  async function verifyWordPressConnection() {
    if (!workspaceId || !csrf) return;
    setWordPressBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/integrations/wordpress/connection/verify?workspace_id="+encodeURIComponent(workspaceId)+(wordpressProjectId ? "&project_id="+encodeURIComponent(wordpressProjectId) : ""),csrf,{method:"POST"});
      const result = await api<{connected:boolean;inherited_from_workspace?:boolean;connection?:{id:string;site_url:string;username:string;status:string;project_id?:string|null}}>("/api/v1/integrations/wordpress/connection?workspace_id="+encodeURIComponent(workspaceId)+(wordpressProjectId ? "&project_id="+encodeURIComponent(wordpressProjectId) : ""),csrf);
      setWordPressConnection(result);
      setNotice("WordPress authentication verified.");
    } catch (err) { setError(err instanceof Error ? err.message : "WordPress verification failed."); }
    finally { setWordPressBusy(false); }
  }

  async function sendWordPressDraft(item: ContentBrief) {
    if (!workspaceId || !csrf) return;
    setWordPressBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/integrations/wordpress/articles/"+encodeURIComponent(item.id)+"/send-draft?workspace_id="+encodeURIComponent(workspaceId),csrf,{method:"POST"});
      const result = await api<{items:ContentBrief[]}>("/api/v1/content-briefs?workspace_id="+encodeURIComponent(workspaceId),csrf);
      setContentBriefs(result.items || []);
      setNotice("Article transferred to WordPress as a private draft. It is not public.");
    } catch (err) { setError(err instanceof Error ? err.message : "WordPress draft transfer failed."); }
    finally { setWordPressBusy(false); }
  }

  async function publishWordPressArticle(item: ContentBrief) {
    if (!workspaceId || !csrf || !window.confirm("Publish this approved article publicly on WordPress? This action makes it visible to site visitors.")) return;
    setWordPressBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/integrations/wordpress/articles/"+encodeURIComponent(item.id)+"/publish",csrf,{method:"POST",body:JSON.stringify({workspace_id:workspaceId,confirm_publish:true})});
      const result = await api<{items:ContentBrief[]}>("/api/v1/content-briefs?workspace_id="+encodeURIComponent(workspaceId),csrf);
      setContentBriefs(result.items || []);
      setNotice("WordPress article published.");
    } catch (err) { setError(err instanceof Error ? err.message : "WordPress publishing failed."); }
    finally { setWordPressBusy(false); }
  }

  async function disconnectWordPress() {
    if (!workspaceId || !csrf || !window.confirm("Disconnect WordPress and permanently remove the saved application password?")) return;
    setWordPressBusy(true); setError(""); setNotice("");
    try {
      const result = await api<{disconnected:boolean;fallback_restored?:boolean;pinned_articles?:boolean}>("/api/v1/integrations/wordpress/connection?workspace_id="+encodeURIComponent(workspaceId)+(wordpressProjectId ? "&project_id="+encodeURIComponent(wordpressProjectId) : ""),csrf,{method:"DELETE"});
      setWordPressConnection({connected:false});
      setNotice(result.pinned_articles
        ? "WordPress credentials revoked. Existing articles remain pinned to this project site; reconnect it before transferring more articles."
        : result.fallback_restored
          ? "Project-specific WordPress override removed. New articles can use the workspace default site where configured."
          : "WordPress connection removed. Existing WordPress posts are unchanged.");
    } catch (err) { setError(err instanceof Error ? err.message : "WordPress disconnect failed."); }
    finally { setWordPressBusy(false); }
  }

  async function reviewContentArticle(item: ContentBrief, decision: "approved" | "rejected") {
    if (!workspaceId || !csrf) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/content-briefs/" + encodeURIComponent(item.id) + "/article/review", csrf, {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspaceId, decision }),
      });
      const result = await api<{ items: ContentBrief[] }>("/api/v1/content-briefs?workspace_id=" + encodeURIComponent(workspaceId), csrf);
      setContentBriefs(result.items || []);
      setNotice(decision === "approved" ? "Article approved editorially. No CMS publishing occurred." : "Article returned for revision.");
    } catch (err) { setError(err instanceof Error ? err.message : "Article review could not be completed."); }
    finally { setBusy(false); }
  }

  async function runProjectGrowthReview(event: FormEvent<HTMLFormElement>, project: Project) {
    event.preventDefault();
    if (!workspaceId || !csrf || !project.website_url) return;
    const requestedWorkspaceId = workspaceId;
    const form = new FormData(event.currentTarget);
    const targetQueries = String(form.get("target_queries") || "").split(/[\r\n,]+/).map(value => value.trim()).filter(Boolean);
    if (!targetQueries.length) { setError("Enter at least one target search query."); return; }
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<GrowthReviewResult>("/api/v1/website-audits/growth-review", csrf, {
        method: "POST",
        body: JSON.stringify({ workspace_id: requestedWorkspaceId, project_id: project.id, target_queries: targetQueries, max_pages: 8, idempotency_key: "growth-review-" + crypto.randomUUID() }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setGrowthReviewResult(result);
      setNotice(result.notice);
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Website growth review could not be completed.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function createProspect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/prospects", csrf, { method: "POST", body: JSON.stringify({
        workspace_id: requestedWorkspaceId, name: prospectName, company: prospectCompany,
        contact_email: prospectEmail || null, contact_phone_e164: prospectPhone || null, website_url: prospectWebsite,
        evidence_url: evidenceUrl, fit_reason: fitReason, verified_facts: [],
      }) });
      if (requestedWorkspaceId !== workspaceId) return;
      setProspectName(""); setProspectCompany(""); setProspectEmail(""); setProspectPhone(""); setProspectWebsite(""); setEvidenceUrl(""); setFitReason("");
      setNotice("Prospect saved with its evidence URL.");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) { if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Prospect could not be saved."); }
    finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }


  async function importProspectsCsv(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (!file || !workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    if (file.size > 1_000_000) { setError("CSV must be 1 MB or smaller."); return; }
    setBusy(true); setError(""); setNotice("");
    try {
      const csvText = await file.text();
      const result = await api<{ created: number; duplicates: number; invalid_count: number; invalid: Array<{row:number;reason:string}> }>("/api/v1/prospects/import.csv?workspace_id="+encodeURIComponent(requestedWorkspaceId), csrf, {
        method: "POST", headers: { "Content-Type": "text/csv" }, body: csvText,
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("CSV import finished: "+result.created+" added, "+result.duplicates+" duplicate evidence rows skipped, "+result.invalid_count+" invalid rows skipped.");
      if (result.invalid.length) setError("Invalid CSV rows: "+result.invalid.map(item=>item.row).join(", "));
      await loadCrmPage(0);
    } catch (err) { if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "CSV import could not be completed."); }
    finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function loadCrmPage(nextOffset: number) {
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    const requestedToken = csrf;
    const requestedSequence = ++crmLoadSequenceRef.current;
    setBusy(true); setError("");
    try {
      const params = new URLSearchParams({ workspace_id: requestedWorkspaceId, limit: String(crmPageSize), offset: String(Math.max(0, nextOffset)) });
      if (prospectSearch.trim()) params.set("search", prospectSearch.trim());
      if (prospectStageFilter !== "all") params.set("stage", prospectStageFilter);
      const result = await api<{ items: Prospect[]; total: number; offset: number }>("/api/v1/prospects?" + params.toString(), requestedToken);
      if (requestedWorkspaceId !== workspaceId || requestedSequence !== crmLoadSequenceRef.current) return;
      setProspects(result.items || []); setCrmOffset(result.offset || 0); setCrmTotal(result.total || 0);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId && requestedSequence === crmLoadSequenceRef.current) setError(err instanceof Error ? err.message : "CRM search could not be completed.");
    } finally {
      if (requestedWorkspaceId === workspaceId && requestedSequence === crmLoadSequenceRef.current) setBusy(false);
    }
  }

  async function searchCrmProspects(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await loadCrmPage(0);
  }

  async function saveProspectDetails(event: FormEvent<HTMLFormElement>, prospect: Prospect) {
    event.preventDefault();
    if (!workspaceId || !csrf || !["owner","admin","member"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")) return;
    const requestedWorkspaceId = workspaceId;
    const form = new FormData(event.currentTarget);
    const payload = {
      workspace_id: requestedWorkspaceId,
      name: String(form.get("name") || "").trim(),
      company: String(form.get("company") || "").trim(),
      role: String(form.get("role") || "").trim() || null,
      contact_email: String(form.get("contact_email") || "").trim() || null,
      contact_phone_e164: String(form.get("contact_phone_e164") || "").trim() || null,
      website_url: String(form.get("website_url") || "").trim(),
      evidence_url: String(form.get("evidence_url") || "").trim(),
      fit_reason: String(form.get("fit_reason") || "").trim(),
    };
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/prospects/" + encodeURIComponent(prospect.id), csrf, { method: "PATCH", body: JSON.stringify(payload) });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("CRM contact details and evidence updated for " + prospect.name + ".");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Prospect details could not be updated.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function archiveProspect(prospect: Prospect) {
    if (!workspaceId || !csrf || !["owner", "admin"].includes(workspaces.find(w => w.id === workspaceId)?.role || "")) return;
    const requestedWorkspaceId = workspaceId;
    if (!window.confirm("Archive " + prospect.name + " from the active CRM? Historical campaign and delivery records are retained; this does not send or delete any message.")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/prospects/" + encodeURIComponent(prospect.id) + "?workspace_id=" + encodeURIComponent(requestedWorkspaceId), csrf, { method: "DELETE" });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice(prospect.name + " was archived from the active CRM. Historical records remain available.");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Prospect could not be archived.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function saveProspectNotes(event: FormEvent<HTMLFormElement>, prospect: Prospect) {
    event.preventDefault();
    if (!workspaceId || !csrf || !["owner", "admin", "member"].includes(workspaces.find(w => w.id === workspaceId)?.role || "")) return;
    const requestedWorkspaceId = workspaceId;
    const form = new FormData(event.currentTarget);
    const notes = String(form.get("notes") || "").trim();
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/prospects/" + encodeURIComponent(prospect.id), csrf, {
        method: "PATCH",
        body: JSON.stringify({ workspace_id: requestedWorkspaceId, notes }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Internal CRM notes saved for " + prospect.name + ".");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Prospect notes could not be saved.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function updateProspectStage(prospect: Prospect, stage: string) {
    if (!workspaceId || !csrf || !["owner", "admin", "member"].includes(workspaces.find(w => w.id === workspaceId)?.role || "")) return;
    const requestedWorkspaceId = workspaceId;
    if (stage === "do_not_contact" && !window.confirm("Mark " + prospect.name + " as Do Not Contact? Future draft and send checks will block outreach.")) {
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/prospects/" + encodeURIComponent(prospect.id), csrf, {
        method: "PATCH",
        body: JSON.stringify({ workspace_id: requestedWorkspaceId, stage }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice(prospect.name + " moved to " + stage.replaceAll("_", " ") + ".");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Prospect stage could not be updated.");
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function setEmailSuppression(prospect: Prospect, suppressed: boolean) {
    if (!workspaceId || !csrf || !["owner", "admin"].includes(workspaces.find(w => w.id === workspaceId)?.role || "")) return;
    const requestedWorkspaceId = workspaceId;
    const action = suppressed ? "suppress future email outreach to" : "allow email outreach to";
    if (!window.confirm("Confirm you want to " + action + " " + prospect.name + "? Existing queued messages will still be rechecked before sending.")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/prospects/" + encodeURIComponent(prospect.id) + "/contact-controls", csrf, {
        method: "PUT",
        body: JSON.stringify({ workspace_id: requestedWorkspaceId, email_suppressed: suppressed, whatsapp_opt_in_confirmed: false }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice(suppressed ? "Email suppression saved. Future draft, queue and send checks will honor it." : "Email suppression removed by an authorized workspace admin.");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Contact controls could not be updated.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function recordWhatsAppConsent(event: FormEvent<HTMLFormElement>, prospect: Prospect) {
    event.preventDefault();
    if (!workspaceId || !csrf || !["owner", "admin"].includes(workspaces.find(w => w.id === workspaceId)?.role || "")) return;
    const requestedWorkspaceId = workspaceId;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const accountId = String(form.get("whatsapp_account_id") || "");
    const evidenceUrl = String(form.get("whatsapp_opt_in_evidence_url") || "").trim();
    if (!accountId || !evidenceUrl.startsWith("https://")) {
      setError("Select an active WhatsApp account and provide an HTTPS consent evidence URL.");
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/prospects/" + encodeURIComponent(prospect.id) + "/contact-controls", csrf, {
        method: "PUT",
        body: JSON.stringify({
          workspace_id: requestedWorkspaceId,
          whatsapp_opt_in_confirmed: true,
          whatsapp_account_id: accountId,
          whatsapp_opt_in_evidence_url: evidenceUrl,
        }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("WhatsApp opt-in evidence saved for the selected account. This records consent; it does not send a message.");
      formElement.reset();
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "WhatsApp consent could not be saved.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function generateDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf || !selectedCampaign || !selectedProspect) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/drafts", csrf, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: requestedWorkspaceId,
          campaign_id: selectedCampaign,
          prospect_id: selectedProspect,
          channel: draftChannel,
          call_to_action: draftCallToAction,
          idempotency_key: "draft-" + crypto.randomUUID(),
        }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setDraftCallToAction("");
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Draft created and placed in the review queue. Nothing was sent.");
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Draft could not be generated.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function queueDraft(draft: Draft) {
    if (!workspaceId || !csrf) return;
    if (!selectedEmailAccountId || !emailAccounts.some(account => account.id === selectedEmailAccountId && account.status === "active")) {
      setError("Connect and successfully test an active SMTP account in this workspace before queuing outreach.");
      return;
    }
    if (!window.confirm(deliveryScheduleLocal ? "Schedule this approved email draft for " + new Date(deliveryScheduleLocal).toLocaleString() + "? It will send automatically when due if the scheduler is configured." : "Queue this approved email draft for immediate eligibility? It will not send until the scheduler runs or an admin chooses Send now.")) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/drafts/" + encodeURIComponent(draft.id) + "/enqueue", csrf, {
        method: "POST", body: JSON.stringify({ workspace_id: requestedWorkspaceId, idempotency_key: "queue-" + crypto.randomUUID(), email_account_id: selectedEmailAccountId || null, scheduled_at: deliveryScheduleLocal ? new Date(deliveryScheduleLocal).toISOString() : null }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice(deliveryScheduleLocal ? "Email scheduled. It will be dispatched automatically when due if CRON_SECRET and the scheduler are configured." : "Email queued and eligible for immediate dispatch by the scheduler or an authorized admin.");
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
    } catch (err) { if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Draft could not be queued."); }
    finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function queueWhatsAppDraft(draft: Draft) {
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    const account = whatsappAccounts.find(item => item.status === "active");
    if (!account) { setError("Verify an active Meta WhatsApp account before queueing this draft."); return; }
    const template = (whatsappTemplates[account.id] || []).find(item => item.status === "approved" && item.verified_at);
    let templateParameters: Record<string, unknown> = {};
    if (template?.components?.some(component => (component.text || "").includes("{{") || component.buttons?.some(button => (button.url || "").includes("{{")))) {
      const raw = window.prompt("Enter WhatsApp template variables as JSON, for example {\"body\":[\"First name\",\"Company\"],\"buttons\":[{\"index\":0,\"sub_type\":\"url\",\"value\":\"tracking-path\"}]}");
      if (raw === null) return;
      try { templateParameters = JSON.parse(raw); } catch { setError("Template variables must be valid JSON."); return; }
    }
    if (!window.confirm("Queue this approved WhatsApp draft using " + account.label + "? The dispatcher re-checks consent, opt-out, campaign status, template/window policy and quota before sending.")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<{ id: string; status: string; dispatch_enabled: boolean }>(
        "/api/v1/integrations/whatsapp/outbound/drafts/" + encodeURIComponent(draft.id) + "/queue",
        csrf,
        { method: "POST", body: JSON.stringify({
          workspace_id: requestedWorkspaceId,
          account_id: account.id,
          idempotency_key: "wa-" + crypto.randomUUID(),
          template_name: template?.template_name || null,
          language_code: template?.language_code || null,
          template_parameters: templateParameters,
        }) },
      );
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("WhatsApp delivery " + result.id.slice(0, 8) + " queued. Dispatch is " + (result.dispatch_enabled ? "enabled by server configuration" : "disabled until the operator explicitly enables it") + ".");
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
    } catch (err) { if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "WhatsApp draft could not be queued."); }
    finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function cancelDelivery(delivery: Delivery) {
    if (!workspaceId || !csrf || !window.confirm("Cancel this queued email? A cancelled delivery will not be sent.")) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/deliveries/" + encodeURIComponent(delivery.id) + "?workspace_id=" + encodeURIComponent(requestedWorkspaceId), csrf, { method: "DELETE" });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Queued email cancelled.");
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
    } catch (err) { if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Delivery could not be cancelled."); }
    finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function rescheduleDelivery(delivery: Delivery) {
    if (!workspaceId || !csrf || !deliveryScheduleLocal) { setError("Choose a future date and time above first."); return; }
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/deliveries/" + encodeURIComponent(delivery.id) + "/schedule", csrf, {
        method: "PATCH", body: JSON.stringify({ workspace_id: requestedWorkspaceId, scheduled_at: new Date(deliveryScheduleLocal).toISOString() }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Queued email rescheduled.");
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
    } catch (err) { if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Delivery could not be rescheduled."); }
    finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function sendDelivery(delivery: Delivery) {
    if (!workspaceId || !csrf || !window.confirm("Send this queued email to the saved recipient now? This contacts a real person and cannot be undone.")) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/deliveries/" + encodeURIComponent(delivery.id) + "/send", csrf, {
        method: "POST", body: JSON.stringify({ workspace_id: requestedWorkspaceId, idempotency_key: "send-" + delivery.id }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Send request processed. SMTP acceptance is not proof of inbox delivery.");
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Send outcome could not be confirmed. Check delivery status before retrying.");
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function loadMoreWhatsAppDeadLetterEvents() {
    if (!workspaceId || !csrf || !whatsappDeadLetterHasMore || whatsappDeadLetterLoadLockRef.current) return;
    const requestedWorkspaceId = workspaceId;
    const requestedOffset = whatsappDeadLetterOffset;
    const requestedToken = csrf;
    const requestedSequence = ++whatsappDeadLetterLoadSequenceRef.current;
    whatsappDeadLetterLoadLockRef.current = true;
    setWhatsappDeadLetterLoadingMore(true);
    try {
      const result = await api<{ items: WhatsAppWebhookEvent[]; next_offset?: number | null; has_more?: boolean }>(
        "/api/v1/integrations/whatsapp/inbox/webhook-events?workspace_id=" + encodeURIComponent(requestedWorkspaceId) + "&state=dead_letter&limit=25&offset=" + requestedOffset,
        requestedToken,
      );
      if (requestedWorkspaceId !== workspaceId || requestedSequence !== whatsappDeadLetterLoadSequenceRef.current) return;
      setWhatsappDeadLetterEvents(current => {
        const known = new Set(current.map(event => event.id));
        return [...current, ...(result.items || []).filter(event => !known.has(event.id))];
      });
      setWhatsappDeadLetterOffset(result.next_offset ?? requestedOffset + (result.items || []).length);
      setWhatsappDeadLetterHasMore(Boolean(result.has_more));
    } catch (err) {
      if (requestedWorkspaceId === workspaceId && requestedSequence === whatsappDeadLetterLoadSequenceRef.current) {
        setError(err instanceof Error ? err.message : "More webhook events could not be loaded.");
      }
    } finally {
      if (requestedSequence === whatsappDeadLetterLoadSequenceRef.current) {
        whatsappDeadLetterLoadLockRef.current = false;
        if (requestedWorkspaceId === workspaceId) setWhatsappDeadLetterLoadingMore(false);
      }
    }
  }

  async function processWhatsAppInboxEvents() {
    if (!workspaceId || !csrf || !window.confirm("Process up to 25 pending inbound Meta webhook events for this workspace's active WhatsApp accounts? This will not send any messages.")) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<{ processed: number; messages_saved: number; statuses_saved: number; unmapped: number; failed: number }>(
        "/api/v1/integrations/whatsapp/inbox/webhook-events/process-pending?workspace_id=" + encodeURIComponent(requestedWorkspaceId) + "&batch_size=25",
        csrf,
        { method: "POST" },
      );
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("WhatsApp inbox processing: " + result.processed + " events processed, " + result.messages_saved + " inbound messages saved, " + result.statuses_saved + " status events saved, " + result.unmapped + " unmapped, " + result.failed + " failed. No messages were sent.");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "WhatsApp inbox processing failed.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function changeWhatsAppSLAPause(conversation: WhatsAppConversation, action: "pause" | "resume") {
    if (!workspaceId || !csrf) return;
    if (action === "pause" && !whatsappSLAPauseReason.trim()) {
      setError("Enter a reason before pausing the SLA clock.");
      return;
    }
    const requestedWorkspaceId = workspaceId;
    const requestedSequence = ++whatsappSLAActionSequenceRef.current;
    const busyEpoch = beginWhatsAppInboxOperation();; setError("");
    try {
      await api("/api/v1/integrations/whatsapp/inbox/conversations/"+encodeURIComponent(conversation.id)+"/sla/"+action+"?workspace_id="+encodeURIComponent(requestedWorkspaceId),csrf,{
        method:"POST",
        ...(action === "pause" ? {body:JSON.stringify({reason:whatsappSLAPauseReason.trim()})} : {}),
      });
      if (requestedSequence !== whatsappSLAActionSequenceRef.current || requestedWorkspaceId !== workspaceId) return;
      setNotice(action === "pause" ? "SLA clock paused with an audit entry." : "SLA clock resumed; paused duration has been excluded.");
      setWhatsappSLAPauseReason("");
      await applyWhatsAppInboxFilters();
      if (requestedWorkspaceId !== workspaceId) return;
      await openWhatsAppConversation(conversation);
    } catch(err) {
      if (requestedSequence === whatsappSLAActionSequenceRef.current && requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Could not update SLA pause state.");
    } finally { endWhatsAppInboxOperation(busyEpoch); }
  }

  async function loadWhatsAppSLA(selectedWorkspaceId = workspaceId, token = csrf) {
    if (!selectedWorkspaceId || !token) return;
    const requestedWorkspaceId = selectedWorkspaceId;
    const requestedSequence = ++whatsappSLALoadSequenceRef.current;
    try {
      const [policy, summary] = await Promise.all([
        api<{warning_minutes:number;breach_minutes:number}>("/api/v1/integrations/whatsapp/inbox/sla/policy?workspace_id="+encodeURIComponent(requestedWorkspaceId),token),
        api<{overdue:number;at_risk:number;within_sla:number;paused:number}>("/api/v1/integrations/whatsapp/inbox/sla/summary?workspace_id="+encodeURIComponent(requestedWorkspaceId),token),
      ]);
      if (requestedSequence !== whatsappSLALoadSequenceRef.current || requestedWorkspaceId !== workspaceIdRef.current) return;
      setWhatsappSLAWarningMinutes(policy.warning_minutes);
      setWhatsappSLABreachMinutes(policy.breach_minutes);
      setWhatsappSLASummary(summary);
      setWhatsappSLAUnavailable(false);
    } catch {
      if (requestedSequence === whatsappSLALoadSequenceRef.current && requestedWorkspaceId === workspaceIdRef.current) setWhatsappSLAUnavailable(true);
    }
  }

  async function saveWhatsAppSLAPolicy() {
    if (!workspaceId || !csrf || whatsappSLABreachMinutes <= whatsappSLAWarningMinutes) {
      setError("SLA breach threshold must be greater than the warning threshold.");
      return;
    }
    const requestedWorkspaceId = workspaceId;
    const requestedSequence = ++whatsappSLAActionSequenceRef.current;
    const policy = { warning_minutes: whatsappSLAWarningMinutes, breach_minutes: whatsappSLABreachMinutes };
    const busyEpoch = beginWhatsAppInboxOperation();; setError("");
    try {
      await api("/api/v1/integrations/whatsapp/inbox/sla/policy?workspace_id="+encodeURIComponent(requestedWorkspaceId),csrf,{
        method:"PUT",body:JSON.stringify(policy),
      });
      if (requestedSequence !== whatsappSLAActionSequenceRef.current || requestedWorkspaceId !== workspaceId) return;
      setNotice("WhatsApp first-response SLA policy saved.");
      await loadWhatsAppSLA();
      if (requestedWorkspaceId !== workspaceId) return;
      await applyWhatsAppInboxFilters();
    } catch(err) {
      if (requestedSequence === whatsappSLAActionSequenceRef.current && requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Could not save WhatsApp SLA policy.");
    } finally { endWhatsAppInboxOperation(busyEpoch); }
  }

  async function applyWhatsAppInboxFilters() {
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    const requestedSequence = ++whatsappInboxQuerySequenceRef.current;
    const requestedDetailSequence = whatsappDetailSequenceRef.current;
    const requestedConversationId = selectedWhatsAppConversation;
    const params = new URLSearchParams({ workspace_id: requestedWorkspaceId, limit: "50" });
    if (whatsappFilterStatus) params.set("inbox_status", whatsappFilterStatus);
    if (whatsappFilterPriority) params.set("priority", whatsappFilterPriority);
    if (whatsappFilterSearch.trim()) params.set("search", whatsappFilterSearch.trim());
    if (whatsappFilterAssignee === "me") params.set("assigned_to_me", "true");
    if (whatsappFilterAssignee === "unassigned") params.set("unassigned", "true");
    if (whatsappFilterAssignee.startsWith("user:")) params.set("assigned_to_user_id", whatsappFilterAssignee.slice(5));
    const busyEpoch = beginWhatsAppInboxOperation();; setError("");
    try {
      const result = await api<{ items: WhatsAppConversation[] }>(
        "/api/v1/integrations/whatsapp/inbox/conversations?" + params.toString(), csrf,
      );
      if (requestedSequence !== whatsappInboxQuerySequenceRef.current || requestedWorkspaceId !== workspaceId) return;
      setWhatsappConversations(result.items || []);
      if (requestedDetailSequence === whatsappDetailSequenceRef.current && requestedConversationId && selectedWhatsAppConversation === requestedConversationId && !(result.items || []).some(item => item.id === requestedConversationId)) {
        whatsappDetailSequenceRef.current += 1;
        setSelectedWhatsAppConversation("");
        setWhatsappMessages([]);
        setWhatsappNotes([]);
        setWhatsappActivity([]);
        setWhatsappNoteDraft("");
      }
    } catch (err) {
      if (requestedSequence === whatsappInboxQuerySequenceRef.current && requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "WhatsApp inbox filters could not be applied.");
    } finally {
      endWhatsAppInboxOperation(busyEpoch);
    }
  }

  async function clearWhatsAppInboxFilters() {
    setWhatsappFilterStatus("");
    setWhatsappFilterPriority("");
    setWhatsappFilterSearch("");
    setWhatsappFilterAssignee("all");
    setWhatsappSelectedSavedView("");
    whatsappDetailSequenceRef.current += 1;
    whatsappInternalNoteSequenceRef.current += 1;
    setSelectedWhatsAppConversation("");
    setWhatsappMessages([]);
    setWhatsappNotes([]);
    setWhatsappActivity([]);
    setWhatsappNoteDraft("");
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    const requestedSequence = ++whatsappInboxQuerySequenceRef.current;
    const busyEpoch = beginWhatsAppInboxOperation();; setError("");
    try {
      const result = await api<{ items: WhatsAppConversation[] }>(
        "/api/v1/integrations/whatsapp/inbox/conversations?workspace_id=" + encodeURIComponent(requestedWorkspaceId) + "&limit=50", csrf,
      );
      if (requestedSequence !== whatsappInboxQuerySequenceRef.current || requestedWorkspaceId !== workspaceId) return;
      setWhatsappConversations(result.items || []);
    } catch (err) {
      if (requestedSequence === whatsappInboxQuerySequenceRef.current && requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "WhatsApp inbox could not be refreshed.");
    } finally {
      endWhatsAppInboxOperation(busyEpoch);
    }
  }

  async function retryWhatsAppDeadLetter(event: WhatsAppWebhookEvent) {
    if (!workspaceId || !csrf || !window.confirm("Requeue this exhausted inbound webhook event for processing? This does not send a WhatsApp message.")) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api<{ state: string }>(
        "/api/v1/integrations/whatsapp/inbox/webhook-events/" + encodeURIComponent(event.id) + "/retry?workspace_id=" + encodeURIComponent(requestedWorkspaceId),
        csrf,
        { method: "POST" },
      );
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Webhook event requeued. Select Process pending inbound events to attempt processing; no message was sent.");
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Webhook event could not be requeued.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function reconcileStaleDeliveries() {
    if (!workspaceId || !csrf || !window.confirm("Mark email sends stuck in processing for at least 15 minutes as uncertain? This will not retry or resend any email.")) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<{ reconciled_count: number; automatic_retry: boolean }>(
        "/api/v1/deliveries/reconcile-stale?workspace_id=" + encodeURIComponent(requestedWorkspaceId) + "&older_than_seconds=900&limit=100",
        csrf,
        { method: "POST" },
      );
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice(result.reconciled_count
        ? result.reconciled_count + " stale delivery record(s) marked uncertain. Check SMTP/provider logs before taking any further action."
        : "No stale processing deliveries found. No messages were sent or retried.");
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Stale delivery reconciliation failed.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function saveDraftEdits(event: FormEvent<HTMLFormElement>, draft: Draft) {
    event.preventDefault();
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    const form = new FormData(event.currentTarget);
    const subject = String(form.get("subject") || "").trim();
    const body = String(form.get("body") || "").trim();
    if (!body || (draft.channel === "email" && !subject)) {
      setError("Email drafts need a subject and every draft needs a message body.");
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/drafts/" + encodeURIComponent(draft.id), csrf, {
        method: "PATCH",
        body: JSON.stringify({ workspace_id: requestedWorkspaceId, subject: draft.channel === "email" ? subject : null, body }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Draft changes saved. The draft remains pending approval and has not been sent.");
      if (requestedWorkspaceId !== workspaceId) return;
      setDraftHistoryOpen(current => ({ ...current, [draft.id]: false }));
      if (requestedWorkspaceId !== workspaceId) return;
      setDraftEvents(current => { const next = { ...current }; delete next[draft.id]; return next; });
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Draft changes could not be saved.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function loadDraftEvents(draft: Draft) {
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    const opening = !draftHistoryOpen[draft.id];
    setDraftHistoryOpen(current => ({ ...current, [draft.id]: opening }));
    if (!opening) return;
    try {
      const result = await api<{ items: DraftEvent[] }>(
        "/api/v1/drafts/" + encodeURIComponent(draft.id) + "/events?workspace_id=" + encodeURIComponent(requestedWorkspaceId) + "&limit=100",
        csrf,
      );
      if (requestedWorkspaceId !== workspaceId) return;
      if (requestedWorkspaceId !== workspaceId) return;
      setDraftEvents(current => ({ ...current, [draft.id]: result.items || [] }));
    } catch (err) {
      if (requestedWorkspaceId !== workspaceId) return;
      if (requestedWorkspaceId !== workspaceId) return;
      setDraftHistoryOpen(current => ({ ...current, [draft.id]: false }));
      setError(err instanceof Error ? err.message : "Draft history could not be loaded.");
    }
  }

  async function regenerateDraft(draft: Draft) {
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    const callToAction = window.prompt("What action should this revised message invite?", "Would you be open to a brief conversation?");
    if (callToAction === null || !callToAction.trim()) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/drafts/" + encodeURIComponent(draft.id) + "/regenerate", csrf, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: requestedWorkspaceId,
          call_to_action: callToAction.trim(),
          idempotency_key: "regenerate-" + crypto.randomUUID(),
        }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Draft regenerated and returned to the same pending review. Nothing was sent.");
      if (requestedWorkspaceId !== workspaceId) return;
      setDraftHistoryOpen(current => ({ ...current, [draft.id]: false }));
      if (requestedWorkspaceId !== workspaceId) return;
      setDraftEvents(current => { const next = { ...current }; delete next[draft.id]; return next; });
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Draft could not be regenerated.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function reviewDraft(draft: Draft, decision: "approved" | "rejected") {
    if (!workspaceId || !csrf || !window.confirm("Confirm " + decision + " for this draft? This does not send a message.")) return;
    const requestedWorkspaceId = workspaceId;
    const note = window.prompt("Optional review note (for the activity history):", "");
    if (note === null) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/drafts/" + encodeURIComponent(draft.id) + "/review", csrf, {
        method: "POST", body: JSON.stringify({ workspace_id: requestedWorkspaceId, decision, note: note.trim() || null }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Draft " + decision + ". No message was sent.");
      if (requestedWorkspaceId !== workspaceId) return;
      setDraftHistoryOpen(current => ({ ...current, [draft.id]: false }));
      if (requestedWorkspaceId !== workspaceId) return;
      setDraftEvents(current => { const next = { ...current }; delete next[draft.id]; return next; });
      if (requestedWorkspaceId === workspaceId) await refresh(requestedWorkspaceId, csrf);
    } catch (err) { if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Draft review failed."); }
    finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function startCheckout() {
    if (!workspaceId || !csrf || !selectedPlan) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<{ checkout_url: string }>("/api/v1/billing/paddle/checkout", csrf, {
        method: "POST", body: JSON.stringify({ workspace_id: requestedWorkspaceId, plan_id: selectedPlan }),
      });
      const checkoutUrl = new URL(result.checkout_url);
      const allowedCheckoutHosts = new Set(["sandbox-checkout.paddle.com", "checkout.paddle.com"]);
      if (checkoutUrl.protocol !== "https:" || checkoutUrl.username || checkoutUrl.password || checkoutUrl.port || !allowedCheckoutHosts.has(checkoutUrl.hostname)) {
        throw new Error("The billing provider returned an unsafe checkout URL.");
      }
      window.location.assign(checkoutUrl.toString());
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Checkout could not be started.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function openBillingPortal() {
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<{ portal_url: string }>(
        "/api/v1/billing/paddle/portal?workspace_id=" + encodeURIComponent(requestedWorkspaceId),
        csrf,
        { method: "POST", body: "{}" },
      );
      const portalUrl = new URL(result.portal_url);
      const allowedPortalHosts = new Set(["customer-portal.sandbox.paddle.com", "customer-portal.paddle.com"]);
      if (portalUrl.protocol !== "https:" || portalUrl.username || portalUrl.password || portalUrl.port || !allowedPortalHosts.has(portalUrl.hostname)) {
        throw new Error("The billing provider returned an unsafe portal URL.");
      }
      window.location.assign(portalUrl.toString());
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Billing portal could not be opened.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function refreshIntegrationStatus() {
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    setIntegrationBusy(true);
    try {
      const result = await api<{ email: { configuration_complete: boolean; missing_fields: string[]; connection_tested?: boolean }; whatsapp: { configuration_complete: boolean; missing_fields: string[]; live_send_enabled: boolean; reason?: string }; ai_outreach?: { configured: boolean; model?: string | null; generation_mode: string; human_approval_required: boolean; automatic_send: boolean } }>(
        "/api/v1/integrations/status?workspace_id=" + encodeURIComponent(requestedWorkspaceId), csrf
      );
      if (requestedWorkspaceId !== workspaceId) return;
      setIntegrationStatus(result);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Provider status could not be loaded.");
    } finally { if (requestedWorkspaceId === workspaceId) setIntegrationBusy(false); }
  }

  async function enqueueGrowthScanNow() {
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/workspace-jobs/website-growth-scan", csrf, {
        method: "POST",
        headers: { "Idempotency-Key": "dashboard-scan-" + window.crypto.randomUUID() },
        body: JSON.stringify({
          workspace_id: requestedWorkspaceId,
          project_id: projects.find(project => project.website_url?.replace(/\/$/, "") === scheduleStartUrl.trim().replace(/\/$/, ""))?.id ?? null,
          start_url: scheduleStartUrl.trim(),
          business_type: scheduleBusinessType.trim(),
          target_market: scheduleTargetMarket.trim(),
          target_queries: scheduleQueries.split(/\r?\n/).map(query => query.trim()).filter(Boolean),
          max_pages: 10,
          max_depth: 2,
        }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("One-off website-growth scan queued. The scan worker must be running before a report can finish.");
      if (requestedWorkspaceId !== workspaceId) return;
      setGrowthJobReport(null);
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Website-growth scan could not be queued.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function openGrowthJobReport(job: GrowthJob) {
    if (!workspaceId || !csrf || job.status !== "succeeded") return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      const detail = await api<{ id: string; status: string; result: unknown }>(
        "/api/v1/workspace-jobs/" + encodeURIComponent(job.id) + "?workspace_id=" + encodeURIComponent(requestedWorkspaceId),
        csrf,
      );
      if (requestedWorkspaceId !== workspaceId) return;
      setGrowthJobReport({ id: detail.id, result: detail.result });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Completed website-growth report loaded.");
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Growth scan report could not be loaded.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function createGrowthSchedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/workspace-growth-schedules", csrf, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: requestedWorkspaceId,
          start_url: scheduleStartUrl.trim(),
          business_type: scheduleBusinessType.trim(),
          target_market: scheduleTargetMarket.trim(),
          target_queries: scheduleQueries.split(/\r?\n/).map(query => query.trim()).filter(Boolean),
          interval_hours: Number(scheduleIntervalHours),
          max_pages: 10,
          max_depth: 2,
        }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Recurring website-growth scan scheduled. The scheduler and scan worker must both be running for scans to execute.");
      if (requestedWorkspaceId !== workspaceId) return;
      setScheduleStartUrl(""); setScheduleBusinessType(""); setScheduleTargetMarket(""); setScheduleQueries("");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Growth schedule could not be created.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function changeGrowthScheduleStatus(schedule: GrowthSchedule, status: "active" | "paused") {
    if (!workspaceId || !csrf || schedule.status === status) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/workspace-growth-schedules/" + encodeURIComponent(schedule.id), csrf, {
        method: "PATCH",
        body: JSON.stringify({ workspace_id: requestedWorkspaceId, status }),
      });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice(status === "paused" ? "Recurring scan paused. Already queued jobs are not cancelled." : "Recurring scan resumed.");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Growth schedule could not be updated.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function deleteGrowthSchedule(schedule: GrowthSchedule) {
    if (!workspaceId || !csrf || !window.confirm("Delete this recurring scan schedule? Jobs already queued will remain in the queue.")) return;
    const requestedWorkspaceId = workspaceId;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/workspace-growth-schedules/" + encodeURIComponent(schedule.id) + "?workspace_id=" + encodeURIComponent(requestedWorkspaceId), csrf, { method: "DELETE" });
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Recurring scan schedule deleted.");
      await refresh(requestedWorkspaceId, csrf);
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Growth schedule could not be deleted.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function deleteAccount() {
    if (!csrf || busy) return;
    const requestedWorkspaceId = workspaceId;
    if (!window.confirm("Delete this account? Sign-in will stop, sessions and pending invitations will be revoked, and sole-member workspaces may be deleted. Shared workspace ownership must be transferred first.")) return;
    const confirmation = window.prompt("Type DELETE MY ACCOUNT to confirm this irreversible action.");
    if (confirmation !== "DELETE MY ACCOUNT") {
      if (requestedWorkspaceId !== workspaceId) return;
      setNotice("Account deletion was not confirmed; no changes were made.");
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      await api<{ status: string }>("/api/v1/account", csrf, { method: "DELETE", body: "{}" });
      router.replace("/login?account_deleted=1");
      router.refresh();
    } catch (err) {
      if (requestedWorkspaceId === workspaceId) setError(err instanceof Error ? err.message : "Account deletion could not be completed.");
    } finally { if (requestedWorkspaceId === workspaceId) setBusy(false); }
  }

  async function logout() {
    setBusy(true);
    try { await api("/api/v1/auth/logout", csrf, { method: "POST", body: "{}" }); }
    catch { /* Expired sessions are cleared by navigating away; never display server details. */ }
    router.replace("/login"); router.refresh();
  }

  const canWrite = workspaces.find(w => w.id === workspaceId)?.role !== "viewer";
  const metricItems: [string, string][] = [
    ["Prospects", "prospects_total"], ["Qualified", "prospects_qualified"],
    ["Active campaigns", "campaigns_active"], ["Drafts awaiting review", "drafts_pending_approval"],
    ["Approved drafts", "drafts_approved"], ["Replies recorded", "inbound_replies"],
    ["WhatsApp inbound", "whatsapp_inbound_messages"], ["WhatsApp status events", "whatsapp_status_events"],
    ["Marked sent", "emails_marked_sent"], ["Failed deliveries", "deliveries_failed"], ["Uncertain outcomes", "deliveries_uncertain"],
  ];

  return <>
    <header className="wrap topbar dashboard-header"><Link className="brand" href="/" aria-label="Outreach Marketing Agent home"><BrandMark/><span className="brand-name">Outreach<small>Marketing Agent</small></span></Link><nav className="nav" aria-label="Workspace navigation"><Link href="/product">Product</Link><Link href="/pricing">Billing</Link><Link href="/platform-admin">Platform admin</Link><button className="button secondary" type="button" onClick={logout} disabled={busy}>Sign out</button></nav></header>
    <main className="wrap dashboard-main">
      <section className="page-head"><p className="eyebrow">Private workspace</p><h1>Your outreach workspace</h1><p className="lead">Signed in as {email || "your account"}. Research, campaigns and approvals stay separated by workspace.</p></section>
      <ErrorNotice message={error} />
      {notice && <p className="notice" role="status" aria-live="polite">{notice}</p>}
      {!loading && workspaces.length > 0 && workspaceId && <nav className="dashboard-shortcuts" aria-label="Jump to workspace tools">
        <a href="#crm">Prospects</a><a href="#campaigns">Campaigns</a><a href="#drafts">Create draft</a><a href="#approvals">Approvals</a><a href="#inbox">Inbox</a><a href="#deliveries">Deliveries</a><a href="#integrations">Connections</a><a href="#billing">Billing</a><a href="#analytics">Analytics</a><a href="#team">Team</a>
      </nav>}
      {loading ? <section className="card" aria-live="polite">Loading secure workspace data…</section> : <>
        {!workspaces.length && <section className="card" role="status"><h2>Start with a workspace</h2><p>Create a workspace below to keep prospects, campaigns, approvals and provider connections organized in one secure place.</p></section>}
        <section className="card" aria-labelledby="workspace-title"><div className="field"><label id="workspace-title" htmlFor="workspace">Active workspace</label><select id="workspace" value={workspaceId} onChange={async e => { const id=e.target.value; const switchSequence=++workspaceSwitchSequenceRef.current; resetWorkspaceScopedState(); workspaceIdRef.current=id; setWorkspaceId(id); setWorkspaceName(workspaces.find(w=>w.id===id)?.name || ""); setLoading(Boolean(id)); try { if (id) await refresh(id, csrf); } finally { if (workspaceSwitchSequenceRef.current===switchSequence) setLoading(false); } }}><option value="">Choose a workspace</option>{workspaces.map(w=><option key={w.id} value={w.id}>{w.name} · {w.role}</option>)}</select></div>
          <form onSubmit={createWorkspace}><div className="field"><label htmlFor="new-workspace-name">Create another workspace</label><input id="new-workspace-name" required maxLength={160} value={newWorkspaceName} onChange={e=>setNewWorkspaceName(e.target.value)} placeholder="Client or business workspace name" /></div><button className="button secondary" type="submit" disabled={busy || !csrf}>Create workspace</button></form>
          {!workspaces.length && <p className="fine">No active workspace membership was returned for this account. Complete account/workspace onboarding before using campaign features.</p>}
          {["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <form onSubmit={saveWorkspaceName}><div className="field"><label htmlFor="workspace-name">Workspace name</label><input id="workspace-name" required maxLength={160} value={workspaceName} onChange={e=>setWorkspaceName(e.target.value)} /></div><button className="button secondary" type="submit" disabled={busy || !workspaceId || !csrf}>Save workspace settings</button></form>}
          <div className="actions"><button className="button secondary" type="button" onClick={downloadAccountExport} disabled={busy || !csrf}>Download my account data</button><button className="button secondary" type="button" onClick={deleteAccount} disabled={busy || !csrf}>Delete my account</button><button className="button secondary" type="button" onClick={() => refresh()} disabled={busy || refreshing || !workspaceId}>{refreshing ? "Refreshing workspace…" : "Refresh workspace"}</button><label className="fine" htmlFor="period">Analytics period</label><select id="period" value={period} onChange={async e => { setPeriod(e.target.value); }}><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option></select></div>
        </section>
        <section className="section" aria-labelledby="email-accounts-title"><h2 id="email-accounts-title">Connected email accounts</h2>
          <p className="fine">SMTP credentials are encrypted at rest. Only supported TLS submission hosts on port 587 are accepted. Connection tests authenticate only and do not send a message.</p>
          <div className="field"><label htmlFor="selected-email-account">Account used for new queued email</label><select id="selected-email-account" value={selectedEmailAccountId} onChange={e=>setSelectedEmailAccountId(e.target.value)}><option value="">Select a connected workspace SMTP account</option>{emailAccounts.filter(account=>account.status==="active").map(account=><option value={account.id} key={account.id}>{account.label} · {account.from_email}</option>)}</select></div>
          <div className="cards">{emailAccounts.length ? emailAccounts.map(account=><article className="card" key={account.id}><h3>{account.label}</h3><p>{account.from_email}</p><p className="fine">{account.smtp_host}:{account.smtp_port} · {account.smtp_username} · {account.status}</p>
            {["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <div className="actions"><button className="button secondary" type="button" disabled={busy || account.status==="disabled"} onClick={()=>beginEmailAccountEdit(account)}>Edit credentials</button><button className="button secondary" type="button" disabled={busy || account.status==="disabled"} onClick={()=>testEmailAccount(account)}>Test connection</button><button className="button secondary" type="button" disabled={busy || account.status!=="active"} onClick={()=>sendEmailAccountTest(account)}>Send test email</button>{account.status!=="disabled" && <button className="button secondary" type="button" disabled={busy} onClick={()=>disableEmailAccount(account)}>Disable</button>}</div>}
          </article>) : <article className="card"><p>No workspace SMTP account is connected. Connect and test your own SMTP account before queuing outreach.</p></article>}</div>
          {editingEmailAccountId && ["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <article className="card" aria-labelledby="edit-email-account-title"><h3 id="edit-email-account-title">Update SMTP account</h3><p className="fine">A new password is required. Saving rotates the credentials and disables delivery until a fresh connection test succeeds.</p><form onSubmit={saveEmailAccountChanges}>
            <div className="field"><label htmlFor="edit-email-account-label">Account label</label><input id="edit-email-account-label" required maxLength={120} value={emailAccountLabel} onChange={e=>setEmailAccountLabel(e.target.value)} /></div>
            <div className="field"><label htmlFor="edit-smtp-host">SMTP provider host</label><select id="edit-smtp-host" value={smtpHost} onChange={e=>setSmtpHost(e.target.value)}><option value="smtp.gmail.com">Gmail / Google Workspace</option><option value="smtp.office365.com">Microsoft 365</option><option value="smtp-mail.outlook.com">Outlook.com</option><option value="smtp.zoho.com">Zoho Mail</option><option value="smtp.zoho.eu">Zoho Mail EU</option><option value="smtp-relay.brevo.com">Brevo</option><option value="smtp.sendgrid.net">SendGrid</option><option value="smtp.mailgun.org">Mailgun</option></select></div>
            <div className="field"><label htmlFor="edit-smtp-username">SMTP username</label><input id="edit-smtp-username" required maxLength={320} value={smtpUsername} onChange={e=>setSmtpUsername(e.target.value)} /></div>
            <div className="field"><label htmlFor="edit-smtp-password">Replacement SMTP password</label><input id="edit-smtp-password" type="password" required minLength={1} maxLength={1024} autoComplete="new-password" value={smtpPassword} onChange={e=>setSmtpPassword(e.target.value)} /></div>
            <div className="field"><label htmlFor="edit-smtp-from-email">Verified sender email</label><input id="edit-smtp-from-email" type="email" required maxLength={320} value={smtpFromEmail} onChange={e=>setSmtpFromEmail(e.target.value)} /></div>
            <div className="field"><label htmlFor="edit-smtp-from-name">Sender name</label><input id="edit-smtp-from-name" required maxLength={200} value={smtpFromName} onChange={e=>setSmtpFromName(e.target.value)} /></div>
            <div className="actions"><button className="button" type="submit" disabled={busy || !csrf}>Save and require connection retest</button><button className="button secondary" type="button" disabled={busy} onClick={()=>{setEditingEmailAccountId(null);setSmtpPassword("");}}>Cancel</button></div>
          </form></article>}
          {["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <details className="card"><summary>Connect an SMTP account</summary><form onSubmit={createEmailAccount}>
            <div className="field"><label htmlFor="email-account-label">Account label</label><input id="email-account-label" required maxLength={120} value={emailAccountLabel} onChange={e=>setEmailAccountLabel(e.target.value)} /></div>
            <div className="field"><label htmlFor="smtp-host">SMTP provider host</label><select id="smtp-host" value={smtpHost} onChange={e=>setSmtpHost(e.target.value)}><option value="smtp.gmail.com">Gmail / Google Workspace</option><option value="smtp.office365.com">Microsoft 365</option><option value="smtp-mail.outlook.com">Outlook.com</option><option value="smtp.zoho.com">Zoho Mail</option><option value="smtp.zoho.eu">Zoho Mail EU</option><option value="smtp-relay.brevo.com">Brevo</option><option value="smtp.sendgrid.net">SendGrid</option><option value="smtp.mailgun.org">Mailgun</option></select></div>
            <div className="field"><label htmlFor="smtp-username">SMTP username</label><input id="smtp-username" required maxLength={320} value={smtpUsername} onChange={e=>setSmtpUsername(e.target.value)} /></div>
            <div className="field"><label htmlFor="smtp-password">SMTP password or provider app password</label><input id="smtp-password" type="password" required maxLength={1024} autoComplete="new-password" value={smtpPassword} onChange={e=>setSmtpPassword(e.target.value)} /></div>
            <div className="field"><label htmlFor="smtp-from-email">Verified sender email</label><input id="smtp-from-email" type="email" required maxLength={320} value={smtpFromEmail} onChange={e=>setSmtpFromEmail(e.target.value)} /></div>
            <div className="field"><label htmlFor="smtp-from-name">Sender name</label><input id="smtp-from-name" required maxLength={200} value={smtpFromName} onChange={e=>setSmtpFromName(e.target.value)} /></div>
            <p className="fine">Use provider-approved SMTP credentials, not your normal account password where app passwords or OAuth are required. Live sending remains subject to server-side approval and quota checks.</p>
            <button className="button" type="submit" disabled={busy || !workspaceId || !csrf}>Encrypt and connect account</button>
          </form></details>}
        </section>
        {["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <section className="section" id="team" aria-labelledby="invitations-title"><h2 id="invitations-title">Team invitations</h2>
          <article className="card"><p className="fine">Invite a teammate by email and assign the least-privileged role they need. Invitation links expire after seven days and can only be accepted by the invited email account.</p>
            <form onSubmit={createInvitation}><div className="field"><label htmlFor="invite-email">Teammate email</label><input id="invite-email" type="email" required maxLength={320} value={inviteEmail} onChange={e=>setInviteEmail(e.target.value)} /></div>
              <div className="field"><label htmlFor="invite-role">Workspace role</label><select id="invite-role" value={inviteRole} onChange={e=>setInviteRole(e.target.value)}><option value="viewer">Viewer — read-only</option><option value="member">Member — create and manage work</option><option value="admin">Admin — workspace administration</option></select></div>
              <button className="button" type="submit" disabled={busy || !workspaceId || !csrf}>Send invitation</button>
            </form>
          </article>
          <h3>Current members</h3>
          <div className="cards">{members.length ? members.map(member=><article className="card" key={member.user_id}><h3>{member.email}</h3><p className="fine">Membership: {member.status} · Role: {member.role}</p><p className="fine">Account: {member.account_status || "unknown"} · Email: {member.email_verified_at ? "verified" : "unverified"} · Last login: {member.last_login_at ? new Date(member.last_login_at).toLocaleString() : "Never"}</p>
            {member.role !== "owner" && <div className="field"><label htmlFor={"role-" + member.user_id}>Role</label><select id={"role-" + member.user_id} value={member.role} disabled={busy || member.status !== "active" || (member.role === "admin" && workspaces.find(w=>w.id===workspaceId)?.role !== "owner")} onChange={e=>changeMemberRole(member,e.target.value)}><option value="viewer">Viewer</option><option value="member">Member</option><option value="admin" disabled={workspaces.find(w=>w.id===workspaceId)?.role !== "owner"}>Admin</option></select></div>}
            {member.role !== "owner" && workspaces.find(w=>w.id===workspaceId)?.role === "owner" && <button className="button secondary" type="button" disabled={busy || member.status !== "active" || member.account_status !== "active" || !member.email_verified_at} onClick={()=>transferOwnership(member)}>Transfer ownership</button>}
            {member.role !== "owner" && <button className="button secondary" type="button" disabled={busy || (member.role === "admin" && workspaces.find(w=>w.id===workspaceId)?.role !== "owner")} onClick={()=>removeMember(member)}>Remove member</button>}
          </article>) : <article className="card"><p>Member list is unavailable or no active memberships were returned.</p></article>}</div>
          <div className="cards">{invitations.length ? invitations.map(invitation=><article className="card" key={invitation.id}><h3>{invitation.invited_email}</h3><p className="fine">Role: {invitation.role} · Status: {invitation.status}</p><p className="fine">Expires: {new Date(invitation.expires_at).toLocaleString()}</p>{invitation.status === "pending" && <button className="button secondary" type="button" disabled={busy} onClick={() => revokeInvitation(invitation)}>Revoke invitation</button>}</article>) : <article className="card"><p>No invitations available for this workspace, or the invitation service is not yet configured.</p></article>}</div>
        </section>}
        <section className="section" id="billing" aria-labelledby="billing-title"><h2 id="billing-title">Plan and billing</h2>
          {plans.length ? <div className="cards">{plans.map(plan=><article className="card" key={plan.id}><h3>{plan.name}</h3><p>{plan.description || "Workspace subscription plan."}</p><p className="fine">{plan.display_price ? plan.display_price + (plan.currency ? " " + plan.currency : "") + (plan.billing_interval ? " / " + plan.billing_interval : "") : "Price is configured in the billing provider; display price has not been supplied."}</p><p className="fine">{plan.checkout_available ? "Provider configuration is present; complete sandbox and production verification before launch." : "Checkout is not enabled until server-side billing configuration is complete."}</p></article>)}</div> : <article className="card"><p>No billing plans are configured yet. Plans must be configured server-side; this screen never invents prices.</p></article>}
          {plans.some(plan=>plan.checkout_available) && <div className="card"><div className="field"><label htmlFor="billing-plan">Choose a plan</label><select id="billing-plan" value={selectedPlan} onChange={e=>setSelectedPlan(e.target.value)}>{plans.filter(plan=>plan.checkout_available).map(plan=><option key={plan.id} value={plan.id}>{plan.name}</option>)}</select></div><div className="actions"><button className="button" type="button" disabled={busy || !workspaceId || !selectedPlan || !["owner"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={startCheckout}>Continue to secure checkout</button><button className="button secondary" type="button" disabled={busy || !workspaceId || !csrf || !["owner"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={openBillingPortal}>Manage billing</button></div><p className="fine">Workspace owner permission is required. Paid access activates only after a verified billing webhook updates server-side subscription state. Manage billing opens the provider portal for an existing Paddle customer.</p></div>}
        </section>
        <section className="section" aria-labelledby="entitlements-title"><h2 id="entitlements-title">Feature access and usage</h2>
          <p className="fine">Access comes from the server-side subscription record. Missing or unavailable billing state does not grant paid access.</p>
          {entitlementsUnavailable && <p className="notice" role="status">One or more entitlement checks are unavailable. Paid actions remain subject to server-side enforcement.</p>}
          <div className="cards">{["ai_draft_generations", "email_sends"].map(feature => {
            const item = entitlements.find(entry => entry.feature === feature);
            const label = feature === "ai_draft_generations" ? "AI draft generation" : "Email sends";
            return <article className="card" key={feature}><h3>{label}</h3>
              <p><strong>{item ? (item.allowed ? "Available" : "Not available") : "Status unavailable"}</strong></p>
              <p className="fine">{item ? (item.allowed ? (item.remaining === null ? "No remaining limit reported by the server." : item.remaining + " uses remaining in the current period.") : "Access decision: " + item.reason.replaceAll("_", " ")) : "Refresh the workspace or contact the operator if this persists."}</p>
            </article>;
          })}</div>
        </section>
        <section className="section" id="analytics" aria-labelledby="metrics-title"><div className="section-head"><h2 id="metrics-title">Recorded activity</h2><p className="fine">Counts from saved records; not estimates of revenue or ROI.</p></div><div className="dashboard-grid">{metricItems.map(([label,key])=><article className="metric" key={key}><strong>{counts[key] ?? "—"}</strong><span>{label}</span></article>)}</div><p className="fine">“Marked sent” means the configured email adapter returned successfully; it does not prove inbox delivery. Clicks, revenue and ROI are not inferred.</p></section>
        <section className="section" aria-labelledby="campaign-performance-title">
          <div className="section-head"><h2 id="campaign-performance-title">Campaign performance</h2><p className="fine">Recorded workflow outcomes for the selected period; these are not revenue attribution.</p></div>
          <div className="cards">{campaignPerformanceUnavailable ? <article className="card"><p>Campaign analytics is temporarily unavailable. Refresh the workspace to try again.</p></article> : campaignPerformance.length ? campaignPerformance.map(item => <article className="card" key={item.id}>
            <p className="eyebrow">{item.status}</p><h3>{item.name}</h3>
            <div className="dashboard-grid">
              {[
                ["Prospects", "prospects_in_campaign"],
                ["Pending review", "drafts_pending_approval"],
                ["Approved", "drafts_approved"],
                ["Email sent", "email_sent_marked"],
                ["Email pending", "email_pending"],
                ["Email failed", "email_failed"],
                ["Email uncertain", "email_uncertain"],
                ["WhatsApp sent or confirmed", "whatsapp_sent_or_confirmed"],
                ["WhatsApp pending", "whatsapp_pending"],
                ["WhatsApp delivered", "whatsapp_delivered"],
                ["WhatsApp read", "whatsapp_read"],
                ["WhatsApp failed", "whatsapp_failed"],
                ["WhatsApp uncertain", "whatsapp_uncertain"],
                ["Prospect replies", "replies_from_campaign_prospects"],
                ["Converted stage", "converted_stage_prospects"],
              ].map(([label, key]) => <div className="metric" key={key}><strong>{item.counts[key] ?? 0}</strong><span>{label}</span></div>)}
            </div>
            <p className="fine">Prospects and draft statuses are based on drafts created during the selected period; delivery and reply counts use their recorded event times. Converted stage is the current CRM label for prospects linked to drafts created during the period, not verified sales revenue.</p>
          </article>) : <article className="card"><p>No campaign performance records are available. Refresh after creating campaigns and recording draft or delivery activity.</p></article>}</div>
        </section>
        <section className="section" aria-labelledby="growth-schedules-title">
          <div className="section-head"><h2 id="growth-schedules-title">Recurring website-growth scans</h2><p className="fine">Scans run only for a domain verified in this workspace. Scheduling queues read-only research; it does not publish changes or send outreach.</p></div>
          {growthSchedulesUnavailable && <p className="notice" role="status">Schedule service is unavailable. Refresh the workspace to try again.</p>}
          <article className="card">
            <form onSubmit={createGrowthSchedule}>
              <div className="field"><label htmlFor="schedule-start-url">Verified website URL</label><input id="schedule-start-url" type="url" required maxLength={2048} placeholder="https://example.com/" value={scheduleStartUrl} onChange={e=>setScheduleStartUrl(e.target.value)} /></div>
              <div className="field"><label htmlFor="schedule-business-type">Business type</label><input id="schedule-business-type" required maxLength={160} value={scheduleBusinessType} onChange={e=>setScheduleBusinessType(e.target.value)} placeholder="B2B SaaS" /></div>
              <div className="field"><label htmlFor="schedule-target-market">Target market</label><input id="schedule-target-market" required maxLength={160} value={scheduleTargetMarket} onChange={e=>setScheduleTargetMarket(e.target.value)} placeholder="United States" /></div>
              <div className="field"><label htmlFor="schedule-target-queries">Research queries (one per line, optional)</label><textarea id="schedule-target-queries" rows={3} maxLength={4000} value={scheduleQueries} onChange={e=>setScheduleQueries(e.target.value)} placeholder={"workflow automation\nCRM integration"} /></div>
              <div className="field"><label htmlFor="schedule-interval">Repeat interval</label><select id="schedule-interval" value={scheduleIntervalHours} onChange={e=>setScheduleIntervalHours(e.target.value)}><option value="24">Daily</option><option value="72">Every 3 days</option><option value="168">Weekly</option><option value="336">Every 2 weeks</option><option value="720">Every 30 days</option></select></div>
              <div className="actions"><button className="button" type="submit" disabled={busy || !workspaceId || !csrf || !canWrite}>Create recurring scan</button><button className="button secondary" type="button" onClick={enqueueGrowthScanNow} disabled={busy || !workspaceId || !csrf || !canWrite || !scheduleStartUrl.trim() || !scheduleBusinessType.trim() || !scheduleTargetMarket.trim()}>Run once now</button></div>
              <p className="fine">Maximum 20 active schedules per workspace. A separate scheduler and website-growth worker must be running for scans to execute.</p>
            </form>
          </article>
          <div className="cards">{growthSchedulesUnavailable ? null : growthSchedules.length ? growthSchedules.map(schedule=><article className="card" key={schedule.id}>
            <p className="eyebrow">{schedule.status}</p><h3>Website growth scan</h3><p>Every {schedule.interval_hours} hours</p>
            <p className="fine">Next scheduled run: {new Date(schedule.next_run_at).toLocaleString()}</p>
            <p className="fine">Last enqueued: {schedule.last_enqueued_at ? new Date(schedule.last_enqueued_at).toLocaleString() : "Not run yet"}</p>
            {schedule.last_attempted_at && <p className="fine">Last attempt: {new Date(schedule.last_attempted_at).toLocaleString()}</p>}
            {schedule.last_error_code && <p className="notice" role="status">Last scheduled run skipped/failed: {schedule.last_error_code.replaceAll("_", " ")}</p>}
            <div className="actions">
              <button className="button secondary" type="button" disabled={busy || !canWrite} onClick={()=>changeGrowthScheduleStatus(schedule,schedule.status==="active" ? "paused" : "active")}>{schedule.status==="active" ? "Pause schedule" : "Resume schedule"}</button>
              {["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <button className="button secondary" type="button" disabled={busy} onClick={()=>deleteGrowthSchedule(schedule)}>Delete</button>}
            </div>
          </article>) : <article className="card"><p>No recurring scans are configured for this workspace.</p></article>}</div>
        </section>
        <section className="section" aria-labelledby="growth-jobs-title">
          <div className="section-head"><h2 id="growth-jobs-title">Recent website-growth jobs</h2><p className="fine">Queued jobs are not complete until the separate scan worker finishes them.</p></div>
          {growthJobsUnavailable && <p className="notice" role="status">Growth job history is unavailable. Refresh the workspace to try again.</p>}
          <div className="cards">{growthJobsUnavailable ? null : growthJobs.length ? growthJobs.map(job=><article className="card" key={job.id}>
            <p className="eyebrow">{job.status}</p><h3>Website growth scan</h3>
            <p className="fine">Created: {new Date(job.created_at).toLocaleString()} · Attempts: {job.attempt_count}/{job.max_attempts}</p>
            {job.finished_at && <p className="fine">Finished: {new Date(job.finished_at).toLocaleString()}</p>}
            {job.error_code && <p className="fine">Failure code: {job.error_code}</p>}
            {job.status === "succeeded" && <button className="button secondary" type="button" disabled={busy} onClick={()=>openGrowthJobReport(job)}>View report</button>}
          </article>) : <article className="card"><p>No website-growth jobs have been queued yet.</p></article>}</div>
          {growthJobReport && <article className="card"><h3>Growth report</h3><p className="fine">Job: {growthJobReport.id}</p><pre style={{overflowX:"auto",maxHeight:"32rem",whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{JSON.stringify(growthJobReport.result, null, 2)}</pre></article>}
        </section>
        <section className="section"><div className="cards">
          <article className="card"><h2>Create campaign</h2><p className="fine">Define the offer and intended audience before generating any draft.</p><form onSubmit={createCampaign}><div className="field"><label htmlFor="campaign-name">Campaign name</label><input id="campaign-name" required maxLength={200} value={campaignName} onChange={e=>setCampaignName(e.target.value)} /></div><div className="field"><label htmlFor="business-name">Business / client</label><input id="business-name" required maxLength={240} value={businessName} onChange={e=>setBusinessName(e.target.value)} /></div><div className="field"><label htmlFor="offer">Offer</label><textarea id="offer" required maxLength={2000} value={offer} onChange={e=>setOffer(e.target.value)} /></div><div className="field"><label htmlFor="target-profile">Target customer profile</label><textarea id="target-profile" required maxLength={2000} value={targetProfile} onChange={e=>setTargetProfile(e.target.value)} /></div><button className="button" disabled={busy || !canWrite || !workspaceId}>Create campaign</button></form></article>
          <article className="card"><h2>Add a prospect</h2><p className="fine">Save public evidence and a clear reason for fit. Website and evidence URLs must use HTTPS.</p><form onSubmit={createProspect}><div className="field"><label htmlFor="prospect-name">Contact / prospect name</label><input id="prospect-name" required maxLength={200} value={prospectName} onChange={e=>setProspectName(e.target.value)} /></div><div className="field"><label htmlFor="prospect-company">Company</label><input id="prospect-company" required maxLength={240} value={prospectCompany} onChange={e=>setProspectCompany(e.target.value)} /></div><div className="field"><label htmlFor="prospect-email">Business email (optional)</label><input id="prospect-email" type="email" maxLength={320} value={prospectEmail} onChange={e=>setProspectEmail(e.target.value)} /></div><div className="field"><label htmlFor="prospect-phone">WhatsApp phone in international E.164 format (optional)</label><input id="prospect-phone" type="tel" inputMode="tel" autoComplete="tel" placeholder="+14155552671" pattern="[+][1-9][0-9]{7,14}" maxLength={16} value={prospectPhone} onChange={e=>setProspectPhone(e.target.value)} /><p className="fine">Store a phone number only when you have a legitimate business reason. A phone number alone is not WhatsApp opt-in.</p></div><div className="field"><label htmlFor="prospect-website">Website URL</label><input id="prospect-website" type="url" required placeholder="https://example.com" value={prospectWebsite} onChange={e=>setProspectWebsite(e.target.value)} /></div><div className="field"><label htmlFor="evidence-url">Evidence URL</label><input id="evidence-url" type="url" required placeholder="https://example.com/about" value={evidenceUrl} onChange={e=>setEvidenceUrl(e.target.value)} /></div><div className="field"><label htmlFor="fit-reason">Why this prospect fits</label><textarea id="fit-reason" required maxLength={2000} value={fitReason} onChange={e=>setFitReason(e.target.value)} /></div><button className="button" disabled={busy || !canWrite || !workspaceId}>Save prospect</button></form></article>
        </div></section>
        <section className="section" aria-labelledby="projects-title"><h2 id="projects-title">Client projects and websites</h2>
          <p className="fine">Keep each client website, audience, offer, language and growth goal in its own workspace-scoped project profile.</p>
          <div className="cards">{projects.length ? projects.map(project=><article className="card" key={project.id}><h3>{project.name}</h3><p>{project.website_url || "No website URL added yet."}</p><p className="fine">{project.business_model} · {project.target_market} · {project.language}</p><p>{project.audience}</p><p className="fine">Goal: {project.conversion_goal || "Not set"}</p>{project.website_url && <p><a href={project.website_url} target="_blank" rel="noreferrer">Open project website</a></p>}
            {["owner","admin","member"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <details><summary>Edit project settings</summary><form onSubmit={event=>updateProject(event,project)}>
              <div className="field"><label>Project name</label><input name="name" required maxLength={160} defaultValue={project.name} /></div>
              <div className="field"><label>Website URL</label><input name="website_url" type="url" maxLength={2048} defaultValue={project.website_url || ""} /></div>
              <div className="field"><label>Business model</label><input name="business_model" maxLength={120} defaultValue={project.business_model} /></div>
              <div className="field"><label>Target market</label><input name="target_market" maxLength={240} defaultValue={project.target_market} /></div>
              <div className="field"><label>Language(s)</label><input name="language" maxLength={120} defaultValue={project.language} /></div>
              <div className="field"><label>Target audience</label><textarea name="audience" maxLength={2000} defaultValue={project.audience} /></div>
              <div className="field"><label>Offer</label><textarea name="offer" maxLength={2000} defaultValue={project.offer} /></div>
              <div className="field"><label>Conversion goal</label><input name="conversion_goal" maxLength={300} defaultValue={project.conversion_goal} /></div>
              <div className="field"><label>Brand voice</label><input name="brand_voice" maxLength={800} defaultValue={project.brand_voice} /></div>
              <div className="field"><label>Competitors (one per line)</label><textarea name="competitors" maxLength={10000} defaultValue={(project.competitors || []).join(String.fromCharCode(10))} /></div>
              <button className="button" type="submit" disabled={busy}>Save changes</button>
            </form></details>}
            {project.website_url && <details><summary>Run evidence-based website growth review</summary><p className="fine">Requires a verified domain and available website-audit entitlement. This creates prioritized recommendations from observed crawl evidence; it does not modify the website.</p><form onSubmit={event=>runProjectGrowthReview(event,project)}><div className="field"><label htmlFor={"growth-queries-"+project.id}>Target search queries (one per line or comma-separated)</label><textarea id={"growth-queries-"+project.id} name="target_queries" required maxLength={4000} rows={3} placeholder={"best service in target city\nrelated service near me"} /></div><button className="button secondary" type="submit" disabled={busy || !csrf || !workspaceId}>Generate growth review</button></form></details>}
            {["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <button className="button secondary" type="button" disabled={busy} onClick={() => archiveProject(project)}>Archive project</button>}</article>) : <article className="card"><p>No project profiles yet. Create one for each website or client business.</p></article>}</div>
          {growthReviewResult?.workspace_id === workspaceId && <article className="card"><h3>Growth review: {growthReviewResult.project_name}</h3><p className="fine">Report ID: {growthReviewResult.report_id} · {growthReviewResult.report.crawl_summary?.pages_crawled ?? 0} pages crawled · Saved for human review</p>{growthReviewResult.report.competitor_discovery && <section><h4>Competitor page candidates</h4><p className="fine">{growthReviewResult.report.competitor_discovery.notice || "Public search candidates; human verification required."}</p>{growthReviewResult.report.competitor_discovery.items?.length ? <ul>{growthReviewResult.report.competitor_discovery.items.map(item => <li key={item.domain}><strong>{item.domain}</strong> — {item.title} (relevance {item.relevance_score})<p className="fine">{item.description}</p><p className="fine">Matched queries: {item.matched_queries.join(", ")} · Candidate only, not a confirmed competitor</p><a href={item.url} target="_blank" rel="noreferrer">Review public result</a></li>)}</ul> : <p className="fine">No competitor candidates are available for this review.</p>}</section>}{growthReviewResult.report.competitor_analysis && <section><h4>Competitor content comparison</h4><p className="fine">{growthReviewResult.report.competitor_analysis.notice || "Comparison uses fetched public page evidence and the client pages crawled."} Pages analyzed: {growthReviewResult.report.competitor_analysis.pages_analyzed ?? 0} / {growthReviewResult.report.competitor_analysis.pages_checked ?? 0}</p>{growthReviewResult.report.competitor_analysis.potential_gaps?.length ? <ul>{growthReviewResult.report.competitor_analysis.potential_gaps.map((gap,index)=><li key={gap.query + gap.competitor_evidence_url + index}><strong>{gap.query}</strong> — potential content coverage gap (priority {gap.priority_score}, {gap.confidence} confidence)<p className="fine">Client coverage: {Math.round(gap.client_coverage * 100)}% · Competitor coverage: {Math.round(gap.competitor_coverage * 100)}%</p><p><a href={gap.competitor_evidence_url} target="_blank" rel="noreferrer">Competitor page evidence</a>{gap.client_evidence_urls.map(url=><span key={url}> · <a href={url} target="_blank" rel="noreferrer">Client page</a></span>)}</p><p className="fine">Potential gap only; review page relevance and content before acting.</p></li>)}</ul> : <p className="fine">No potential content gaps were supported by the pages analyzed.</p>}</section>}{growthReviewResult.report.strategy?.actions?.length ? <div className="cards">{growthReviewResult.report.strategy.actions.map(action=><article className="card" key={action.id}><p className="eyebrow">{action.priority} priority · score {action.priority_score}</p><h4>{action.title}</h4><p>{action.recommended_action}</p><p className="fine">Confidence: {action.confidence}</p><p><a href={action.evidence_url} target="_blank" rel="noreferrer">Review evidence</a></p><button className="button secondary" type="button" disabled={busy || !canWrite} onClick={()=>createContentBrief(action.id)}>Create content brief</button></article>)}</div> : <p>No evidence-backed actions were generated. Check crawl status and domain verification before trying again.</p>}{growthReviewResult.report.strategy?.measurement_plan && <><h4>Measurement plan</h4><ul>{growthReviewResult.report.strategy.measurement_plan.map(item=><li key={item}>{item}</li>)}</ul></>}{growthReviewResult.report.limitations?.map(item=><p className="fine" key={item}>{item}</p>)}</article>}<article className="card"><h3>Editorial content workflow</h3><p className="fine">Saved briefs stay in this workspace for editing and review. Approval does not publish content.</p><section className="card"><h4>WordPress connection</h4><div className="field"><label htmlFor="wordpress-project-scope">WordPress site scope</label><select id="wordpress-project-scope" value={wordpressProjectId} onChange={async event=>{const next=event.target.value;setWordPressProjectId(next);setWordPressConnection(null);setWordPressEditing(false);if(!workspaceId||!csrf)return;setWordPressBusy(true);try{const result=await api<{connected:boolean;inherited_from_workspace?:boolean;connection?:{id:string;site_url:string;username:string;status:string;project_id?:string|null}}>("/api/v1/integrations/wordpress/connection?workspace_id="+encodeURIComponent(workspaceId)+(next ? "&project_id="+encodeURIComponent(next) : ""),csrf);setWordPressConnection(result);}catch(err){setError(err instanceof Error?err.message:"WordPress connection could not be loaded.");}finally{setWordPressBusy(false);}}}><option value="">Workspace default site</option>{projects.map(project=><option key={project.id} value={project.id}>{project.name} · {project.website_url || "No website URL"}</option>)}</select></div><p className="fine">Configure a site per project, or use the workspace default as a fallback. Article delivery automatically selects the connection for that article’s project; this selector only manages connection settings. Create an Application Password in WordPress under Users → Profile → Application Passwords. Use a dedicated user with edit/publish post permissions. Credentials are encrypted; articles transfer as drafts first. The meta description is sent as the WordPress excerpt; SEO-plugin-specific meta fields are not written automatically.</p>{wordpressConnection?.connected && wordpressConnection.connection && !wordpressEditing ? <><p className="fine">{wordpressConnection.connection.site_url} · {wordpressConnection.connection.username} · {wordpressConnection.connection.status}</p>{wordpressConnection.inherited_from_workspace ? <><p className="fine">This project inherits the workspace-default connection. Draft delivery is available only while that connection is verified. It is managed under “Workspace default site”; changing or disconnecting it there affects every project without its own connection.</p>{["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <button className="button secondary" type="button" disabled={wordpressBusy} onClick={()=>setWordPressEditing(true)}>Configure a project-specific site</button>}</> : <div className="actions"><span className="fine">{wordpressConnection.connection.status === "verified" ? "Connection verified" : wordpressConnection.connection.status === "disabled" ? "Disconnected · credentials revoked" : "Verification required"}</span>{["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <>{wordpressConnection.connection.status === "pending" && <button className="button" type="button" disabled={wordpressBusy} onClick={verifyWordPressConnection}>Verify connection</button>}<button className="button secondary" type="button" disabled={wordpressBusy} onClick={()=>setWordPressEditing(true)}>Update credentials</button><button className="button secondary" type="button" disabled={wordpressBusy} onClick={disconnectWordPress}>Disconnect</button></>}</div>}</> : <form onSubmit={saveWordPressConnection}><div className="field"><label htmlFor="wp-site">WordPress site URL</label><input id="wp-site" name="site_url" type="url" required defaultValue={wordpressConnection?.connection?.site_url || ""} placeholder="https://example.com"/></div><div className="field"><label htmlFor="wp-user">WordPress username</label><input id="wp-user" name="username" required defaultValue={wordpressConnection?.connection?.username || ""} autoComplete="username"/></div><div className="field"><label htmlFor="wp-app-password">WordPress Application Password</label><input id="wp-app-password" name="application_password" type="password" required autoComplete="new-password"/></div><button className="button" type="submit" disabled={wordpressBusy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")}>Save encrypted connection</button></form>}</section>{contentBriefs.length === 0 ? <p className="fine">No saved content briefs yet. Create one from a website growth recommendation.</p> : null}<div className="cards">{contentBriefs.map(item=><article className="card" key={item.id}><h4>{item.title}</h4><p className="fine">Status: {item.status.replaceAll("_"," ")}</p>{item.evidence_url && <p><a href={item.evidence_url} target="_blank" rel="noreferrer">Review source evidence</a></p>}{["draft","rejected"].includes(item.status) ? <form onSubmit={event=>updateContentBrief(event,item)}><div className="field"><label htmlFor={"brief-title-"+item.id}>Content title</label><input id={"brief-title-"+item.id} name="title" required maxLength={300} defaultValue={item.title}/></div><div className="field"><label htmlFor={"brief-keyword-"+item.id}>Target keyword</label><input id={"brief-keyword-"+item.id} name="target_keyword" maxLength={300} defaultValue={item.target_keyword}/></div><div className="field"><label htmlFor={"brief-body-"+item.id}>Editorial brief</label><textarea id={"brief-body-"+item.id} name="brief" required maxLength={10000} rows={5} defaultValue={item.brief}/></div><button className="button secondary" type="submit" disabled={busy || !canWrite}>Save and submit for review</button></form> : item.status === "in_review" && ["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") ? <div className="actions"><button className="button" type="button" disabled={busy} onClick={()=>reviewContentBrief(item,"approved")}>Approve brief</button><button className="button secondary" type="button" disabled={busy} onClick={()=>reviewContentBrief(item,"rejected")}>Return for revision</button></div> : <p className="fine">{item.brief}</p>}{item.status === "approved" && (!item.article_status || ["not_generated","rejected"].includes(item.article_status)) && <button className="button secondary" type="button" disabled={busy} onClick={()=>generateContentArticle(item)}>Generate SEO article draft</button>}{item.article_status === "approved" && (!item.cms_status || ["not_sent","failed","draft_created"].includes(item.cms_status)) && editingArticleId !== item.id && <button className="button secondary" type="button" disabled={busy || wordpressBusy} onClick={()=>setEditingArticleId(item.id)}>Edit approved article</button>}{item.article_status && item.article_status !== "not_generated" && <section className="article-editor"><h4>SEO article · {item.article_status.replaceAll("_"," ")}</h4>{item.article_outline?.length ? <><p className="fine">Article structure</p><ul>{item.article_outline.map((heading,index)=><li key={index}>{heading}</li>)}</ul></> : null}{item.internal_link_suggestions?.length ? <><p className="fine">Suggested internal links</p><ul>{item.internal_link_suggestions.map((link,index)=><li key={link.url+index}><a href={link.url} target="_blank" rel="noreferrer">{link.url}</a> — {link.reason}</li>)}</ul></> : null}{(["draft","rejected"].includes(item.article_status) || editingArticleId === item.id) ? <form onSubmit={event=>updateContentArticle(event,item)}><div className="field"><label>Article title</label><input name="article_title" required maxLength={300} defaultValue={item.article_title || item.title}/></div><div className="field"><label>SEO meta title</label><input name="meta_title" required maxLength={70} defaultValue={item.meta_title || ""}/></div><div className="field"><label>SEO meta description</label><textarea name="meta_description" required maxLength={180} rows={2} defaultValue={item.meta_description || ""}/></div><div className="field"><label>Article body (Markdown)</label><textarea name="article_body" required minLength={500} maxLength={40000} rows={18} defaultValue={item.article_body || ""}/></div><button className="button secondary" type="submit" disabled={busy || !canWrite}>Save article and submit for review</button></form> : item.article_status === "in_review" && ["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") ? <div className="actions"><button className="button" type="button" disabled={busy} onClick={()=>reviewContentArticle(item,"approved")}>Approve article</button><button className="button secondary" type="button" disabled={busy} onClick={()=>reviewContentArticle(item,"rejected")}>Return article for revision</button></div> : <pre className="fine" style={{whiteSpace:"pre-wrap"}}>{item.article_body}</pre>}</section>}{item.article_status === "approved" && ["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && (!item.cms_status || ["not_sent","failed","draft_created"].includes(item.cms_status)) && <button className="button secondary" type="button" disabled={wordpressBusy || busy} onClick={()=>sendWordPressDraft(item)}>{item.cms_post_id ? "Update WordPress draft" : "Send to WordPress as draft"}</button>}{item.cms_status && item.cms_status !== "not_sent" && <p className="fine">WordPress: {item.cms_status.replaceAll("_"," ")}{item.cms_post_url ? <> · <a href={item.cms_post_url} target="_blank" rel="noreferrer">Open post</a></> : null}</p>}{item.cms_status === "draft_created" && item.article_status === "approved" && editingArticleId !== item.id && ["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <button className="button" type="button" disabled={wordpressBusy} onClick={()=>publishWordPressArticle(item)}>Publish publicly on WordPress</button>}</article>)}</div></article>
          <article className="card"><h3>Create project profile</h3><form onSubmit={createProject}>
            <div className="field"><label htmlFor="project-name">Project name</label><input id="project-name" required maxLength={160} value={projectName} onChange={e=>setProjectName(e.target.value)} /></div>
            <div className="field"><label htmlFor="project-website">Website URL (optional)</label><input id="project-website" type="url" maxLength={2048} placeholder="https://example.com" value={projectWebsite} onChange={e=>setProjectWebsite(e.target.value)} /></div>
            <div className="field"><label htmlFor="project-model">Business model</label><input id="project-model" maxLength={120} value={projectBusinessModel} onChange={e=>setProjectBusinessModel(e.target.value)} /></div>
            <div className="field"><label htmlFor="project-market">Target market</label><input id="project-market" maxLength={240} value={projectMarket} onChange={e=>setProjectMarket(e.target.value)} /></div>
            <div className="field"><label htmlFor="project-language">Language(s)</label><input id="project-language" maxLength={120} value={projectLanguage} onChange={e=>setProjectLanguage(e.target.value)} /></div>
            <div className="field"><label htmlFor="project-audience">Target audience</label><textarea id="project-audience" maxLength={2000} value={projectAudience} onChange={e=>setProjectAudience(e.target.value)} /></div>
            <div className="field"><label htmlFor="project-offer">Offer / value proposition</label><textarea id="project-offer" maxLength={2000} value={projectOffer} onChange={e=>setProjectOffer(e.target.value)} /></div>
            <div className="field"><label htmlFor="project-goal">Conversion goal</label><input id="project-goal" maxLength={300} value={projectGoal} onChange={e=>setProjectGoal(e.target.value)} /></div>
            <div className="field"><label htmlFor="project-voice">Brand voice</label><input id="project-voice" maxLength={800} value={projectBrandVoice} onChange={e=>setProjectBrandVoice(e.target.value)} /></div>
            <div className="field"><label htmlFor="project-competitors">Competitors (one per line, optional)</label><textarea id="project-competitors" maxLength={10000} value={projectCompetitors} onChange={e=>setProjectCompetitors(e.target.value)} /></div>
            <button className="button" type="submit" disabled={busy || !canWrite || !workspaceId || !csrf}>Save project profile</button>
          </form></article>
        </section>
        <section className="section" id="campaigns"><h2>Campaigns</h2><div className="cards">{campaigns.length ? campaigns.map(c=><article className="card" key={c.id}><h3>{c.name}</h3><p>{c.client_business}</p><p className="fine">{c.target_customer_profile}</p><span className="fine">{c.status || "Saved campaign"}</span><details><summary>Edit campaign settings</summary><form onSubmit={event=>updateCampaign(event,c)}><div className="field"><label htmlFor={"campaign-edit-name-"+c.id}>Campaign name</label><input id={"campaign-edit-name-"+c.id} name="name" required maxLength={200} defaultValue={c.name} /></div><div className="field"><label htmlFor={"campaign-edit-business-"+c.id}>Business / client</label><input id={"campaign-edit-business-"+c.id} name="client_business" required maxLength={240} defaultValue={c.client_business} /></div><div className="field"><label htmlFor={"campaign-edit-offer-"+c.id}>Offer</label><textarea id={"campaign-edit-offer-"+c.id} name="client_offer" required maxLength={2000} defaultValue={c.client_offer} /></div><div className="field"><label htmlFor={"campaign-edit-audience-"+c.id}>Target customer profile</label><textarea id={"campaign-edit-audience-"+c.id} name="target_customer_profile" required maxLength={2000} defaultValue={c.target_customer_profile} /></div><div className="field"><label htmlFor={"campaign-edit-status-"+c.id}>Status</label><select id={"campaign-edit-status-"+c.id} name="status" defaultValue={c.status || "draft"}><option value="draft">Draft</option><option value="active">Active</option><option value="paused">Paused</option><option value="archived">Archived</option></select></div><button className="button secondary" type="submit" disabled={busy || !["owner","admin","member"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")}>Save campaign</button></form></details></article>) : <article className="card"><p>No campaigns yet. Create one above to organize outreach.</p></article>}</div></section>
        <section className="section" aria-labelledby="followups-title">
          <h2 id="followups-title">Campaign follow-up sequences</h2>
          <p className="fine">Build timed email or WhatsApp follow-ups. When a step is due, the scheduler creates a draft for review. Every step still requires approval and a separate queue action; this automation never sends without those gates.</p>
          <article className="card">
            <h3>Create a follow-up sequence</h3>
            <form onSubmit={createFollowupSequence}>
              <div className="field"><label htmlFor="followup-campaign">Campaign</label><select id="followup-campaign" required value={followupCampaignId} onChange={event=>setFollowupCampaignId(event.target.value)}><option value="">Choose an active campaign</option>{campaigns.filter(c=>c.status==="active").map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
              <div className="field"><label htmlFor="followup-name">Sequence name</label><input id="followup-name" required maxLength={200} value={followupName} onChange={event=>setFollowupName(event.target.value)} placeholder="Three-touch follow-up" /></div>
              <div className="field"><label htmlFor="followup-channel">Channel</label><select id="followup-channel" value={followupChannel} onChange={event=>setFollowupChannel(event.target.value)}><option value="email">Email</option><option value="whatsapp">WhatsApp</option></select></div>
              <div className="field"><label htmlFor="followup-steps">Steps (JSON; 1–10 steps)</label><textarea id="followup-steps" rows={8} maxLength={30000} value={followupStepsJson} onChange={event=>setFollowupStepsJson(event.target.value)} /><p className="fine">Allowed placeholders: {"{{first_name}}"}, {"{{company}}"}, {"{{business}}"}, {"{{offer}}"}. Delay is minutes after enrollment for step 1, then after the previous confirmed delivery. Email steps require a subject template.</p></div>
              <button className="button" type="submit" disabled={busy || !workspaceId || !csrf || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") || !campaigns.some(c=>c.id===followupCampaignId && c.status==="active")}>Create and activate sequence</button>
            </form>
          </article>
          <div className="cards">{followupSequences.length ? followupSequences.map(sequence=><article className="card" key={sequence.id}>
            <h3>{sequence.name}</h3><p className="fine">{sequence.channel.toUpperCase()} · {sequence.status} · {sequence.enrollment_count || 0} enrolled · {sequence.active_count || 0} active · {sequence.awaiting_approval_count || 0} awaiting approval</p>
            <div className="actions"><button className="button secondary" type="button" disabled={busy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={()=>setFollowupStatus(sequence,sequence.status==="active"?"paused":"active")}>{sequence.status==="active"?"Pause sequence":"Activate / resume"}</button><button className="button secondary" type="button" disabled={busy} onClick={()=>loadFollowupEnrollments(sequence)}>View enrollments</button></div>
            <div className="field"><label htmlFor={"followup-prospect-"+sequence.id}>Enroll prospect</label><select id={"followup-prospect-"+sequence.id} value={followupProspectId} onChange={event=>setFollowupProspectId(event.target.value)}><option value="">Choose prospect</option>{prospects.map(prospect=><option key={prospect.id} value={prospect.id}>{prospect.name} · {prospect.company}</option>)}</select></div>
            <button className="button secondary" type="button" disabled={busy || !followupProspectId || sequence.status!=="active" || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={()=>enrollFollowup(sequence)}>Enroll prospect</button>
            {followupEnrollments[sequence.id] && <div><h4>Enrollments</h4>{followupEnrollments[sequence.id].length ? followupEnrollments[sequence.id].map(enrollment=><div key={enrollment.id} style={{borderTop:"1px solid var(--border)",padding:"0.65rem 0"}}><strong>{enrollment.prospect_name || enrollment.company || enrollment.prospect_id}</strong><p className="fine">Step {enrollment.current_step} · {enrollment.status}{enrollment.next_run_at?" · next " + new Date(enrollment.next_run_at).toLocaleString():""}{enrollment.last_error_code?" · " + enrollment.last_error_code:""}{enrollment.pause_reason?" · pause: " + enrollment.pause_reason:""}</p>{["active","awaiting_approval"].includes(enrollment.status) && <button className="button secondary" type="button" disabled={busy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={()=>setFollowupEnrollmentStatus(sequence,enrollment,"paused")}>Pause prospect</button>}{enrollment.status==="paused" && ["operator_paused","pending_draft_conflict"].includes(enrollment.pause_reason || "") && <button className="button secondary" type="button" disabled={busy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={()=>setFollowupEnrollmentStatus(sequence,enrollment,"active")}>{enrollment.pause_reason==="pending_draft_conflict"?"Resume after clearing pending draft":"Resume prospect"}</button>}{enrollment.status==="paused" && ["delivery_failed","delivery_uncertain"].includes(enrollment.pause_reason || "") && enrollment.current_delivery_id && <div className="stack"><p className="fine">Provider review required for delivery {enrollment.current_delivery_id}. Unknown outcomes must remain paused.</p><label>Resolution reason<input value={followupResolutionReason[enrollment.id] || ""} onChange={e=>setFollowupResolutionReason(current=>({...current,[enrollment.id]:e.target.value}))} minLength={12} maxLength={2000} /></label><label>HTTPS evidence URL<input type="url" value={followupResolutionEvidence[enrollment.id] || ""} onChange={e=>setFollowupResolutionEvidence(current=>({...current,[enrollment.id]:e.target.value}))} placeholder="https://provider.example/event/..." /></label><button className="button secondary" type="button" disabled={busy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={()=>resolveFollowupDelivery(sequence,enrollment,"delivered")}>Confirm delivered</button><button className="button secondary" type="button" disabled={busy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={()=>resolveFollowupDelivery(sequence,enrollment,"not_delivered")}>Confirm not delivered and stop</button></div>}</div>) : <p className="fine">No enrollments yet.</p>}</div>}
          </article>) : <article className="card"><p>No follow-up sequences yet. Create one under an active campaign.</p></article>}</div>
        </section>
        <section className="section" aria-labelledby="website-audit-title"><h2 id="website-audit-title">Website growth audit</h2>
          <article className="card">
            <p className="fine">Read-only crawl for websites you own or are authorized to audit. Workspace admin verification is required before scanning a domain.</p>
            {["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <form onSubmit={createDomainChallenge}>
              <div className="field"><label htmlFor="domain-name">Domain you control</label><input id="domain-name" required minLength={3} maxLength={253} value={domainName} onChange={e=>setDomainName(e.target.value)} placeholder="example.com" /></div>
              <button className="button secondary" type="submit" disabled={domainBusy || busy || !workspaceId || !csrf}>Create DNS TXT challenge</button>
            </form>}
            {domainChallenge && <div className="notice" role="status"><h3>Publish this DNS TXT record</h3><p>Type: {domainChallenge.dns_record.type}</p><p>Name: <code>{domainChallenge.dns_record.record_name}</code></p><p>Value: <code>{domainChallenge.dns_record.record_value}</code></p><p className="fine">Expires: {domainChallenge.expires_at}. {domainChallenge.instructions}</p><button className="button" type="button" onClick={verifyDomain} disabled={domainBusy}>Verify public DNS</button></div>}
            <form onSubmit={runWebsiteAudit}><div className="field"><label htmlFor="audit-url">Verified website URL</label><input id="audit-url" type="url" required minLength={8} maxLength={2048} value={auditUrl} onChange={e=>setAuditUrl(e.target.value)} placeholder="https://example.com/" /></div>
              <button className="button" type="submit" disabled={auditBusy || busy || !workspaceId || !csrf || !auditUrl.trim()}>{auditBusy ? "Auditing…" : "Run read-only SEO crawl"}</button>
            </form>
          </article>
          {auditHistory.length > 0 && <article className="card"><h3>Recent saved audit reports</h3><div className="cards">{auditHistory.map(item=><article className="card" key={item.id}><p>{item.start_url}</p><p className="fine">{item.status} · {new Date(item.created_at).toLocaleString()}</p><button className="button secondary" type="button" disabled={auditBusy} onClick={()=>openSavedAudit(item.id)}>Open report</button></article>)}</div></article>}
          {auditReport && <div className="section"><article className="card"><h3>Audit overview</h3><p>{auditReport.report.crawl_skipped ? "Crawl skipped: " + (auditReport.report.reason || "safety check") : (auditReport.report.crawl?.pages_crawled ?? 0) + " pages crawled"}</p><p className="fine">{auditReport.report.start_url}</p></article>
            {auditReport.report.crawl?.aggregate_findings?.length ? <div className="cards">{auditReport.report.crawl.aggregate_findings.map(finding=><article className="card" key={finding.code}><p className="eyebrow">{finding.severity} · {finding.occurrences} occurrence(s)</p><h3>{finding.title}</h3><p className="fine">Finding: {finding.code}</p>{finding.evidence_urls.slice(0,3).map(url=><p key={url}><a href={url} target="_blank" rel="noreferrer">Open evidence page</a></p>)}</article>)}</div> : <p className="fine">No aggregate findings were returned, or the crawl did not complete.</p>}
            {(auditReport.report.limitations || []).length > 0 && <p className="fine">Limitations: {(auditReport.report.limitations || []).join(" ")}</p>}
          </div>}
        </section>
        <section className="section" aria-labelledby="research-title"><h2 id="research-title">Discover prospects from public sources</h2>
          <article className="card"><p className="fine">Search returns source-linked suggestions only. Results are not saved automatically; verify fit and evidence before adding a prospect to the CRM.</p>
            <form onSubmit={searchProspects}><div className="field"><label htmlFor="research-query">Business, audience and market query</label><textarea id="research-query" required minLength={3} maxLength={400} value={researchQuery} onChange={e=>setResearchQuery(e.target.value)} placeholder="Describe the type of business, creator, publisher or potential customer you want to find." /></div>
              <button className="button" type="submit" disabled={researchBusy || busy || !workspaceId || !csrf || !canWrite}>{researchBusy ? "Searching public sources…" : "Search public web"}</button>
            </form>
          </article>
          {researchResults.length > 0 && <div className="cards">{researchResults.map(item=><article className="card" key={item.url}><h3><a href={item.url} target="_blank" rel="noreferrer">{item.title}</a></h3><p>{item.description || "No search description supplied."}</p><p className="fine">Domain: {item.domain || "Domain unavailable"} · Relevance hint: {typeof item.relevance_score === "number" ? item.relevance_score + "/100" : "not scored"} · Review required · Not saved to CRM</p>{item.relevance_reasons && item.relevance_reasons.length > 0 && <p className="fine">{item.relevance_reasons.join(" · ")}</p>}<button className="button secondary" type="button" disabled={busy || !canWrite} onClick={() => { setProspectName(item.title.slice(0, 200)); setProspectCompany(""); setProspectWebsite(""); setProspectEmail(""); setProspectPhone(""); setEvidenceUrl(item.url); setFitReason((item.description || "Public search result; verify relevance before saving.").slice(0, 2000)); setNotice("Search evidence copied to the prospect form. Verify the real contact name, company, website and relevance before saving."); document.getElementById("prospect-name")?.scrollIntoView({ behavior: "smooth", block: "center" }); }}>Prepare CRM record for review</button></article>)}</div>}

          <article className="card" aria-labelledby="influencer-research-title">
            <h3 id="influencer-research-title">Discover public creator profiles</h3>
            <p className="fine">Find public Instagram, TikTok, YouTube, LinkedIn and X profile candidates. Relevance is based on search text only; it is not an influence or quality score.</p>
            <form onSubmit={searchInfluencers}>
              <div className="field"><label htmlFor="influencer-query">Creator niche, audience and market</label><input id="influencer-query" required minLength={3} maxLength={400} value={influencerQuery} onChange={event=>setInfluencerQuery(event.target.value)} placeholder="e.g. Karachi food creators reviewing independent restaurants" /></div>
              <div className="field"><label htmlFor="influencer-platforms">Platforms (choose one or more)</label><select id="influencer-platforms" multiple size={5} value={influencerPlatforms} onChange={event=>setInfluencerPlatforms(Array.from(event.target.selectedOptions, option=>option.value))}><option value="instagram">Instagram</option><option value="tiktok">TikTok</option><option value="youtube">YouTube</option><option value="linkedin">LinkedIn</option><option value="x">X</option></select></div>
              <button className="button" type="submit" disabled={influencerBusy || researchBusy || busy || !workspaceId || !csrf || !canWrite || influencerPlatforms.length===0}>{influencerBusy ? "Finding public creator profiles…" : "Discover creators"}</button>
            </form>
            {influencerResults.length > 0 && <div className="cards">{influencerResults.map(item=><article className="card" key={item.profile_url}>
              <h4><a href={item.profile_url} target="_blank" rel="noreferrer">{item.title}</a></h4>
              <p className="fine">{item.platform.toUpperCase()} · Topical relevance: {item.relevance_score}/100 · Human review required</p>
              <p>{item.description || "No public search description supplied."}</p>
              <p className="fine">Audience metrics unavailable: follower counts, average views and engagement rate have not been verified. Review the profile and current audience data independently.</p>
            </article>)}</div>}
          </article>
        </section>
        <section className="section" id="crm"><h2>Prospect CRM</h2>
          <article className="card"><form onSubmit={searchCrmProspects}>
            <div className="field"><label htmlFor="crm-search">Search contacts</label><input id="crm-search" value={prospectSearch} onChange={event=>setProspectSearch(event.target.value)} placeholder="Name, company, email, phone, role or website" maxLength={120}/></div>
            <div className="field"><label htmlFor="crm-stage-filter">Filter by stage</label><select id="crm-stage-filter" value={prospectStageFilter} onChange={event=>setProspectStageFilter(event.target.value)}><option value="all">All stages</option>{["new","qualified","approved","contacted","replied","converted","disqualified","do_not_contact"].map(stage=><option key={stage} value={stage}>{stage.replaceAll("_"," ")}</option>)}</select></div>
            <div className="actions"><button className="button" type="submit" disabled={busy || !workspaceId || !csrf}>Search CRM</button><button className="button secondary" type="button" disabled={busy} onClick={()=>{setProspectSearch("");setProspectStageFilter("all");void loadCrmPage(0);}}>Clear filters</button><a className="button secondary" href={"/api/v1/prospects/export.csv?workspace_id="+encodeURIComponent(workspaceId)+(prospectStageFilter!=="all"?"&stage="+encodeURIComponent(prospectStageFilter):"")+(prospectSearch.trim()?"&search="+encodeURIComponent(prospectSearch.trim()):"")}>Export filtered CSV</a><label className="button secondary" htmlFor="crm-csv-import">Import CSV</label><input id="crm-csv-import" type="file" accept=".csv,text/csv" onChange={importProspectsCsv} disabled={busy || !canWrite} style={{display:"none"}} /></div>
          </form><p className="fine">Showing {prospects.length ? crmOffset + 1 : 0}–{crmOffset + prospects.length} of {crmTotal} matching active prospects. Pages contain up to 50 records.</p></article>
          <div className="actions" aria-label="CRM pagination"><button className="button secondary" type="button" disabled={busy || crmOffset===0} onClick={()=>void loadCrmPage(Math.max(0,crmOffset-crmPageSize))}>Previous</button><span className="fine">Page {Math.floor(crmOffset/crmPageSize)+1} of {Math.max(1,Math.ceil(crmTotal/crmPageSize))}</span><button className="button secondary" type="button" disabled={busy || crmOffset+prospects.length>=crmTotal} onClick={()=>void loadCrmPage(crmOffset+crmPageSize)}>Next</button></div>
          <div className="cards">{prospects.length ? prospects.map(p=><article className="card" key={p.id}><h3>{p.name}</h3><p>{p.role ? p.role + " · " : ""}{p.company}</p><p>{p.fit_reason}</p><p className="fine">Stage: {p.stage || "new"}{p.contact_email ? " · " + p.contact_email : ""}</p><div className="field"><label htmlFor={"prospect-stage-"+p.id}>CRM stage</label><select id={"prospect-stage-"+p.id} value={p.stage || "new"} disabled={busy || !["owner","admin","member"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onChange={event=>updateProspectStage(p,event.target.value)}><option value="new">New</option><option value="qualified">Qualified</option><option value="approved">Approved</option><option value="contacted">Contacted</option><option value="replied">Replied</option><option value="converted">Converted</option><option value="disqualified">Disqualified</option><option value="do_not_contact">Do not contact</option></select></div>{p.contact_email && <p className="fine">Email outreach: {p.email_suppressed ? "Suppressed" : "Not suppressed"}</p>}{p.contact_phone_e164 && <p className="fine">WhatsApp consent: {p.whatsapp_opt_in_documented ? (p.whatsapp_opt_in_account_id ? ("Evidence recorded for " + (whatsappAccounts.find(account=>account.id===p.whatsapp_opt_in_account_id)?.label || "a previously configured account")) : "Evidence recorded, but account scope is missing — reconfirm before use") : "Not documented"}</p>}<p><a href={p.evidence_url} target="_blank" rel="noreferrer">Open evidence source</a></p><details><summary>Edit contact and evidence details</summary><form onSubmit={event=>saveProspectDetails(event,p)}>
          <div className="field"><label htmlFor={"crm-name-"+p.id}>Contact name</label><input id={"crm-name-"+p.id} name="name" required maxLength={200} defaultValue={p.name}/></div>
          <div className="field"><label htmlFor={"crm-company-"+p.id}>Company</label><input id={"crm-company-"+p.id} name="company" required maxLength={240} defaultValue={p.company}/></div>
          <div className="field"><label htmlFor={"crm-role-"+p.id}>Role</label><input id={"crm-role-"+p.id} name="role" maxLength={160} defaultValue={p.role || ""}/></div>
          <div className="field"><label htmlFor={"crm-email-"+p.id}>Email</label><input id={"crm-email-"+p.id} name="contact_email" type="email" maxLength={320} defaultValue={p.contact_email || ""}/></div>
          <div className="field"><label htmlFor={"crm-phone-"+p.id}>Phone (E.164)</label><input id={"crm-phone-"+p.id} name="contact_phone_e164" pattern="\\+[1-9][0-9]{7,14}" maxLength={16} defaultValue={p.contact_phone_e164 || ""}/></div>
          <div className="field"><label htmlFor={"crm-website-"+p.id}>Website URL (HTTPS)</label><input id={"crm-website-"+p.id} name="website_url" type="url" required pattern="https://.+" maxLength={2048} defaultValue={p.website_url}/></div>
          <div className="field"><label htmlFor={"crm-evidence-"+p.id}>Evidence URL (HTTPS)</label><input id={"crm-evidence-"+p.id} name="evidence_url" type="url" required pattern="https://.+" maxLength={2048} defaultValue={p.evidence_url}/></div>
          <div className="field"><label htmlFor={"crm-fit-"+p.id}>Fit reason</label><textarea id={"crm-fit-"+p.id} name="fit_reason" required maxLength={2000} defaultValue={p.fit_reason}/></div>
          <button className="button secondary" type="submit" disabled={busy || !canWrite}>Save contact details</button>
        </form></details><details><summary>Internal CRM notes</summary><form onSubmit={event=>saveProspectNotes(event,p)}><div className="field"><label htmlFor={"prospect-notes-"+p.id}>Notes (private to this workspace)</label><textarea id={"prospect-notes-"+p.id} name="notes" maxLength={5000} rows={3} defaultValue={p.notes || ""} /></div><button className="button secondary" type="submit" disabled={busy || !["owner","admin","member"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")}>Save notes</button></form></details>{["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <div className="actions">{p.contact_email && <button className="button secondary" type="button" disabled={busy} onClick={() => setEmailSuppression(p, !p.email_suppressed)}>{p.email_suppressed ? "Allow email outreach" : "Suppress email outreach"}</button>}<button className="button secondary" type="button" disabled={busy} onClick={() => archiveProspect(p)}>Archive prospect</button></div>}{p.contact_phone_e164 && ["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <details><summary>Record WhatsApp opt-in evidence</summary><p className="fine">Only record this after the contact has actually opted in. A phone number or public profile is not consent. Outbound WhatsApp sending is controlled by the server-side dispatch flag and remains off by default.</p><form onSubmit={event=>recordWhatsAppConsent(event,p)}><div className="field"><label htmlFor={"whatsapp-account-"+p.id}>WhatsApp business account</label><select id={"whatsapp-account-"+p.id} name="whatsapp_account_id" required defaultValue=""><option value="">Choose an active account</option>{whatsappAccounts.filter(account=>account.status==="active").map(account=><option key={account.id} value={account.id}>{account.label} · {account.phone_number_id}</option>)}</select></div><div className="field"><label htmlFor={"whatsapp-consent-evidence-"+p.id}>Consent evidence URL (HTTPS)</label><input id={"whatsapp-consent-evidence-"+p.id} name="whatsapp_opt_in_evidence_url" type="url" required pattern="https://.+" maxLength={2048} placeholder="https://example.com/consent-record" /></div><button className="button secondary" type="submit" disabled={busy || !whatsappAccounts.some(account=>account.status==="active")}>Save documented opt-in</button></form></details>}</article>) : <article className="card"><p>No prospects saved yet.</p></article>}</div></section>
        <section className="section" id="drafts"><h2>Prepare an outreach draft</h2><article className="card"><p className="fine">Draft generation uses workspace entitlements and saved prospect evidence. Every draft enters review; this form never sends a message.</p><form onSubmit={generateDraft}><div className="field"><label htmlFor="draft-campaign">Campaign</label><select id="draft-campaign" required value={selectedCampaign} onChange={e=>setSelectedCampaign(e.target.value)}><option value="">Choose a campaign</option>{campaigns.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></div><div className="field"><label htmlFor="draft-prospect">Prospect</label><select id="draft-prospect" required value={selectedProspect} onChange={e=>setSelectedProspect(e.target.value)}><option value="">Choose a prospect</option>{prospects.map(p=><option key={p.id} value={p.id}>{p.name} · {p.company}</option>)}</select></div><div className="field"><label htmlFor="draft-channel">Channel</label><select id="draft-channel" value={draftChannel} onChange={e=>setDraftChannel(e.target.value)}><option value="email">Email</option><option value="whatsapp">WhatsApp draft (eligibility checked by backend)</option></select></div><div className="field"><label htmlFor="draft-cta">Call to action</label><textarea id="draft-cta" required maxLength={500} value={draftCallToAction} onChange={e=>setDraftCallToAction(e.target.value)} placeholder="Suggest a short, relevant next step" /></div><button className="button" disabled={busy || !canWrite || !workspaceId || !campaigns.length || !prospects.length}>Generate draft for review</button></form></article></section>
        <section className="section" id="approvals"><h2>Draft review queue</h2><p className="fine">Approving a draft does not send it. Choose an optional future send time below before queueing an approved email.</p><div className="field"><label htmlFor="delivery-schedule-at">Schedule approved emails (optional)</label><input id="delivery-schedule-at" type="datetime-local" value={deliveryScheduleLocal} min={new Date(Date.now()+60000).toISOString().slice(0,16)} onChange={event=>setDeliveryScheduleLocal(event.target.value)} /><p className="fine">Leave blank for immediate eligibility. The selected time uses your browser's local timezone.</p></div><div className="cards">{drafts.length ? drafts.map(d=><article className="card" key={d.id}><p className="eyebrow">{d.channel || "Outreach"} · {d.status}</p><h3>{d.subject || d.prospect_name || "Outreach draft"}</h3><p>{d.body || "Draft content is not available."}</p><div className="actions"><button type="button" className="button secondary" aria-expanded={!!draftHistoryOpen[d.id]} onClick={() => loadDraftEvents(d)} disabled={busy}> {draftHistoryOpen[d.id] ? "Hide activity" : "View activity"} </button></div>{draftHistoryOpen[d.id] && <div className="fine" aria-live="polite"><h4>Draft activity</h4>{draftEvents[d.id]?.length ? <ol>{draftEvents[d.id].map((event,index)=><li key={d.id+"-"+index}><strong>{event.event_type.replaceAll("_"," ")}</strong>{event.note ? " — "+event.note : ""}{event.created_at ? " · "+new Date(event.created_at).toLocaleString() : ""}{event.actor_id ? " · Actor "+event.actor_id.slice(0,8) : ""}</li>)}</ol> : <p>No activity entries are available.</p>}</div>}{d.status === "approved" && d.channel === "email" && <div className="actions"><button type="button" className="button secondary" disabled={busy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={() => queueDraft(d)}>Queue email</button></div>}{d.status === "approved" && d.channel === "whatsapp" && <div className="actions"><button type="button" className="button secondary" disabled={busy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") || !whatsappAccounts.some(account=>account.status==="active")} onClick={() => queueWhatsAppDraft(d)}>Queue WhatsApp</button></div>}{d.status === "pending_approval" && <><div className="actions"><button type="button" className="button secondary" disabled={busy || !["owner","admin","member"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={() => regenerateDraft(d)}>Regenerate draft</button></div><details><summary>Edit draft before approval</summary><form onSubmit={event=>saveDraftEdits(event,d)}><div className="field"><label htmlFor={"draft-subject-"+d.id}>Email subject (email only)</label><input id={"draft-subject-"+d.id} name="subject" maxLength={300} required={d.channel==="email"} disabled={busy || !["owner","admin","member"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} defaultValue={d.subject || ""} /></div><div className="field"><label htmlFor={"draft-body-"+d.id}>Message body</label><textarea id={"draft-body-"+d.id} name="body" required maxLength={10000} rows={6} disabled={busy || !["owner","admin","member"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} defaultValue={d.body || ""} /></div><button className="button secondary" type="submit" disabled={busy || !["owner","admin","member"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")}>Save draft edits</button></form></details><div className="actions"><button type="button" className="button" disabled={busy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={() => reviewDraft(d,"approved")}>Approve draft</button><button type="button" className="button secondary" disabled={busy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={() => reviewDraft(d,"rejected")}>Reject</button></div></>}</article>) : <article className="card"><p>No drafts yet. Draft generation requires configured paid entitlements and eligible prospect evidence.</p></article>}</div></section>
        <section className="section" id="integrations" aria-labelledby="integrations-title"><h2 id="integrations-title">Provider connections</h2>
          <article className="card">
            <p className="fine">Workspace SMTP accounts are encrypted at rest, tested before activation, and selected for queued outreach. Campaigns require an active SMTP account configured in this workspace; platform SMTP is reserved for transactional messages such as verification and password reset. Use Test connection and Send test email here to validate your own account. Provider diagnostics never return credentials.</p>
            <div className="actions">
              <button className="button secondary" type="button" onClick={refreshIntegrationStatus} disabled={integrationBusy || !workspaceId || !csrf}>Refresh status</button>
              
            </div>
            {integrationStatus ? <div className="cards">
              <div className="metric"><strong>{integrationStatus.email?.configuration_complete ? "Configured" : "Incomplete"}</strong><span>Email / SMTP</span><p className="fine">{integrationStatus.email?.configuration_complete ? "An active workspace SMTP account has passed its connection test." : "Connect and test a workspace SMTP account above. Missing: " + (integrationStatus.email?.missing_fields || []).join(", ")}</p></div>
              <div className="metric"><strong>{integrationStatus.whatsapp?.live_send_enabled ? "Enabled" : "Disabled"}</strong><span>Official WhatsApp Business</span><p className="fine">{integrationStatus.whatsapp?.reason || "Configure Meta app credentials, verify a workspace account, and complete Meta's external onboarding."} {integrationStatus.whatsapp?.active_workspace_accounts ?? 0} active account(s); dispatch {integrationStatus.whatsapp?.dispatch_feature_enabled ? "enabled" : "disabled"}.</p></div>
              <div className="metric"><strong>{integrationStatus.ai_outreach?.configured ? "AI provider configured" : "Template fallback"}</strong><span>AI outreach generation</span><p className="fine">{integrationStatus.ai_outreach?.configured ? "Personalized copy uses the configured " + (integrationStatus.ai_outreach.model || "AI model") + " provider, then enters mandatory human review." : "Configure AI_API_KEY to enable provider-generated copy. Evidence-grounded templates remain available; every draft still requires human approval."}</p></div>
            </div> : <p className="fine">Provider status has not been loaded for this workspace.</p>}
            <h3>Official Meta WhatsApp accounts</h3>
            <p className="fine">Add an access token from Meta Business settings and the matching WhatsApp Business Account and phone-number IDs. Tokens are encrypted at rest and never shown again. New accounts stay pending verification. Account verification also subscribes the app to WABA webhooks; outbound dispatch is a separate server-side setting.</p>
            <div className="cards">{whatsappAccounts.length ? whatsappAccounts.map(account => <article className="card" key={account.id}>
              <h4>{account.label}</h4><p className="fine">WABA ID: {account.waba_id} · Phone number ID: {account.phone_number_id}</p>
              <p className="fine">Status: {account.status}</p>
              {["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && account.status === "pending_verification" && <button className="button" type="button" disabled={busy} onClick={() => verifyWhatsAppAccount(account)}>Verify with Meta</button>}
              {["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && account.status === "active" && <button className="button" type="button" disabled={busy} onClick={() => syncWhatsAppTemplates(account)}>Sync approved templates</button>}{["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && account.status !== "disabled" && <button className="button secondary" type="button" disabled={busy} onClick={() => rotateWhatsAppToken(account)}>Rotate access token</button>}
              {whatsappTemplates[account.id]?.length ? <section aria-label={"Templates for " + account.label}>
                <h5>Message templates ({whatsappTemplates[account.id].length})</h5>
                <ul>{whatsappTemplates[account.id].map(template => <li key={template.template_name + ":" + template.language_code}>
                  <strong>{template.template_name}</strong> · {template.language_code} · {template.category}
                  <span className="fine"> — Meta: {template.provider_status || template.status}; local status: {template.status}
                    {template.verified_at ? "; verified " + new Date(template.verified_at).toLocaleString() : ""}
                  </span>
                </li>)}</ul>
              </section> : <p className="fine">No synchronized templates are recorded for this account yet.</p>}
                            {["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && account.status !== "disabled" && <button className="button secondary" type="button" disabled={busy} onClick={() => disableWhatsAppAccount(account)}>Disable account</button>}
            </article>) : <article className="card"><p>No WhatsApp Business accounts registered for this workspace.</p></article>}</div>
            <h3>WhatsApp inbox</h3>
            <p className="fine">Inbound messages received by the configured Meta webhook appear here. Processing is workspace-scoped and admin-triggered; approved templates can be synchronized by workspace admins; outbound dispatch is off by default and requires explicit server activation.</p>
            {["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <div className="actions"><button className="button secondary" type="button" disabled={busy || !workspaceId || !csrf || !whatsappAccounts.some(account=>account.status==="active")} onClick={processWhatsAppInboxEvents}>Process pending inbound events</button><p className="fine">Processes at most 25 pending events for active accounts in this workspace. Does not send messages.</p></div>}
            {whatsappDeadLetterEvents.length > 0 && <article className="card">
              <h4>Webhook events needing attention ({whatsappDeadLetterEvents.length})</h4>
              <p className="fine">These inbound events exhausted automatic attempts. Requeue only after reviewing the configuration; requeueing does not send a message.</p>
              <div className="cards">{whatsappDeadLetterEvents.map(event=><article className="card" key={event.id}>
                <p className="eyebrow">{event.event_kind} · Dead letter</p>
                <p className="fine">Received: {event.received_at} · Phone number ID: {event.phone_number_id || "unmapped"}</p>
                {event.processing_error_code && <p className="fine">Last error: {event.processing_error_code}</p>}
                <button className="button secondary" type="button" disabled={busy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={()=>retryWhatsAppDeadLetter(event)}>Requeue event</button>
              </article>)}</div>
              {whatsappDeadLetterHasMore && <button className="button secondary" type="button" disabled={whatsappDeadLetterLoadingMore || busy} onClick={loadMoreWhatsAppDeadLetterEvents}>{whatsappDeadLetterLoadingMore ? "Loading…" : "Load more webhook events"}</button>}
            </article>}
            <div className="cards">
              <article className="card">
                <h4>Conversations ({whatsappConversations.length})</h4>
                <div className="form-grid" style={{marginBottom:"0.75rem"}}>
                  <label>Assigned teammate
                    <select className="input" value={whatsappFilterAssignee} onChange={event=>setWhatsappFilterAssignee(event.target.value)}>
                      <option value="all">All conversations</option><option value="me">Assigned to me</option><option value="unassigned">Unassigned</option>
                      {members.filter(member=>member.status==="active").map(member=><option key={member.user_id} value={"user:"+member.user_id}>{member.email}</option>)}
                    </select>
                  </label>
                  <label>Status
                    <select className="input" value={whatsappFilterStatus} onChange={event=>setWhatsappFilterStatus(event.target.value)}>
                      <option value="">All statuses</option><option value="open">Open</option><option value="pending">Pending</option><option value="resolved">Resolved</option>
                    </select>
                  </label>
                  <label>Priority
                    <select className="input" value={whatsappFilterPriority} onChange={event=>setWhatsappFilterPriority(event.target.value)}>
                      <option value="">All priorities</option><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option>
                    </select>
                  </label>
                  <label>Search contact, company or message
                    <input className="input" value={whatsappFilterSearch} maxLength={200} onChange={event=>setWhatsappFilterSearch(event.target.value)} onKeyDown={event=>{if(event.key==="Enter"){event.preventDefault();void applyWhatsAppInboxFilters();}}} placeholder="Name, phone, company or text" />
                  </label>
                  <div className="grid grid-2">
                    <label>Saved views
                      <select className="input" value={whatsappSelectedSavedView} onFocus={()=>void loadWhatsAppSavedViews()} onChange={event=>void applyWhatsAppSavedView(event.target.value)}>
                        <option value="">Choose saved view</option>{whatsappSavedViews.map(view=><option key={view.id} value={view.id}>{view.name}</option>)}
                      </select>
                    </label>
                    <label>Save current filters
                      <input className="input" value={whatsappSavedViewName} maxLength={80} onChange={event=>setWhatsappSavedViewName(event.target.value)} placeholder="e.g. Urgent unassigned"/>
                    </label>
                  </div>
                  <div style={{display:"flex",gap:"0.5rem",alignItems:"end",flexWrap:"wrap"}}>
                    <button className="button secondary" type="button" disabled={whatsappInboxBusy || !whatsappSavedViewName.trim()} onClick={saveWhatsAppCurrentView}>Save view</button>
                    {whatsappSelectedSavedView && <button className="button secondary" type="button" onClick={()=>deleteWhatsAppSavedView(whatsappSelectedSavedView)}>Delete saved view</button>}
                  </div>
                  <div style={{display:"flex",gap:"0.5rem",alignItems:"end"}}>
                    <button className="button" type="button" disabled={whatsappInboxBusy} onClick={applyWhatsAppInboxFilters}>Apply filters</button>
                    <button className="button secondary" type="button" disabled={whatsappInboxBusy} onClick={clearWhatsAppInboxFilters}>Clear</button>
                  </div>
                </div>
                <div className="stack" style={{border:"1px solid var(--border)",borderRadius:"0.75rem",padding:"0.75rem",marginBottom:"0.75rem"}}>
                  <strong>First-response SLA</strong>
                  {whatsappSLAUnavailable ? <p className="fine" role="status">SLA summary and policy could not be loaded. Inbox conversations remain available; use Refresh workspace to retry.</p> : <span className="fine">Overdue: {whatsappSLASummary.overdue} · At risk: {whatsappSLASummary.at_risk} · Within SLA: {whatsappSLASummary.within_sla} · Paused: {whatsappSLASummary.paused}</span>}
                  {whatsappSavedViewsUnavailable && <p className="fine" role="status">Saved inbox views could not be loaded. Existing inbox filters remain usable; refresh the workspace to retry.</p>}
                  {["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <div className="grid grid-2">
                    <label>Warning after (minutes)<input className="input" type="number" min="1" max="1440" value={whatsappSLAWarningMinutes} onChange={event=>setWhatsappSLAWarningMinutes(Number(event.target.value))}/></label>
                    <label>Overdue after (minutes)<input className="input" type="number" min="2" max="10080" value={whatsappSLABreachMinutes} onChange={event=>setWhatsappSLABreachMinutes(Number(event.target.value))}/></label>
                    <button className="button secondary" type="button" disabled={whatsappInboxBusy || whatsappSLABreachMinutes<=whatsappSLAWarningMinutes} onClick={saveWhatsAppSLAPolicy}>Save SLA policy</button>
                  </div>}
                </div>
                {["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <div className="stack" style={{border:"1px solid var(--border)",borderRadius:"0.75rem",padding:"0.75rem",marginBottom:"0.75rem"}}>
                  <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:"0.5rem",flexWrap:"wrap"}}>
                    <strong>Bulk actions ({selectedWhatsAppBulkIds.length} selected)</strong>
                    <button className="button secondary" type="button" disabled={whatsappInboxBusy || !whatsappConversations.length} onClick={()=>setSelectedWhatsAppBulkIds(selectedWhatsAppBulkIds.length===whatsappConversations.length?[]:whatsappConversations.map(item=>item.id))}>{selectedWhatsAppBulkIds.length===whatsappConversations.length?"Clear selection":"Select visible"}</button>
                  </div>
                  <div className="grid grid-3">
                    <label>Assign to
                      <select className="input" value={whatsappBulkAssignee} onChange={event=>setWhatsappBulkAssignee(event.target.value)}>
                        <option value="__unchanged__">Leave unchanged</option><option value="">Unassigned</option>
                        {members.filter(member=>member.status==="active").map(member=><option key={member.user_id} value={member.user_id}>{member.email}</option>)}
                      </select>
                    </label>
                    <label>Status
                      <select className="input" value={whatsappBulkStatus} onChange={event=>setWhatsappBulkStatus(event.target.value)}>
                        <option value="">Leave unchanged</option><option value="open">Open</option><option value="pending">Pending</option><option value="resolved">Resolved</option>
                      </select>
                    </label>
                    <label>Priority
                      <select className="input" value={whatsappBulkPriority} onChange={event=>setWhatsappBulkPriority(event.target.value)}>
                        <option value="">Leave unchanged</option><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option>
                      </select>
                    </label>
                  </div>
                  <button className="button" type="button" disabled={whatsappInboxBusy || !selectedWhatsAppBulkIds.length} onClick={applyWhatsAppBulkUpdate}>Apply to selected</button>
                </div>}
                {whatsappConversations.length ? whatsappConversations.map(conversation => <div key={conversation.id} style={{display:"flex",gap:"0.5rem",alignItems:"stretch",marginBottom:"0.5rem"}}>
                  {["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <label style={{display:"flex",alignItems:"center",padding:"0 0.5rem"}}><input type="checkbox" aria-label={"Select "+(conversation.prospect_name || conversation.wa_id)} checked={selectedWhatsAppBulkIds.includes(conversation.id)} disabled={whatsappInboxBusy} onChange={event=>setSelectedWhatsAppBulkIds(ids=>event.target.checked?[...ids,conversation.id]:ids.filter(id=>id!==conversation.id))}/></label>}
                  <button
                  className={"button " + (selectedWhatsAppConversation === conversation.id ? "" : "secondary")}
                  type="button" key={conversation.id} disabled={whatsappInboxBusy}
                  onClick={() => openWhatsAppConversation(conversation)}
                  style={{display:"block",width:"100%",textAlign:"left",marginBottom:"0.5rem",whiteSpace:"normal"}}
                >
                  <strong>{conversation.prospect_name || conversation.wa_id}</strong>
                  <span className="fine" style={{display:"block"}}>{(conversation.inbox_status || "open").toUpperCase()} · {(conversation.priority || "normal").toUpperCase()} · {conversation.assigned_to_user_id ? (members.find(member=>member.user_id===conversation.assigned_to_user_id)?.email || "Assigned teammate") : "Unassigned"}</span>
                  <span style={{display:"block"}}>{conversation.account_label} · {conversation.prospect_company || "Unmatched contact"}</span>
                  <span style={{display:"block"}}>{conversation.last_message_text || ("Latest message type: " + (conversation.last_message_type || "not available"))}</span>
                  <span className="fine" style={{display:"block"}}>First-response SLA: {({within_sla:"Within SLA",at_risk:"At risk",overdue:"Overdue",paused:"Paused",met:"Response sent",resolved:"Resolved",not_applicable:"No inbound message"} as Record<string,string>)[conversation.sla_state || "not_applicable"]}{conversation.sla_due_at && conversation.sla_state!=="met" && conversation.sla_state!=="resolved" ? " · due " + new Date(conversation.sla_due_at).toLocaleString() : ""}</span>
                  </button></div>) : <p className="fine">No inbound conversations have been processed yet.</p>}
              </article>
              <article className="card">
                <h4>Conversation workspace</h4>
                {selectedWhatsAppConversation && (() => {
                  const conversation = whatsappConversations.find(item => item.id === selectedWhatsAppConversation);
                  if (!conversation) return null;
                  const canManage = ["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "");
                  return <div className="stack" style={{marginBottom:"1rem"}}>
                    <div className="grid grid-3">
                      <label>Assignee
                        <select className="input" disabled={!canManage || whatsappInboxBusy} value={conversation.assigned_to_user_id || ""} onChange={event=>updateWhatsAppConversation(conversation,{assigned_to_user_id:event.target.value || null})}>
                          <option value="">Unassigned</option>
                          {members.filter(member=>member.status==="active").map(member=><option key={member.user_id} value={member.user_id}>{member.email} ({member.role})</option>)}
                        </select>
                      </label>
                      <label>Status
                        <select className="input" disabled={!canManage || whatsappInboxBusy} value={conversation.inbox_status || "open"} onChange={event=>updateWhatsAppConversation(conversation,{inbox_status:event.target.value as "open"|"pending"|"resolved"})}>
                          <option value="open">Open</option><option value="pending">Pending</option><option value="resolved">Resolved</option>
                        </select>
                      </label>
                      <label>Priority
                        <select className="input" disabled={!canManage || whatsappInboxBusy} value={conversation.priority || "normal"} onChange={event=>updateWhatsAppConversation(conversation,{priority:event.target.value as "low"|"normal"|"high"|"urgent"})}>
                          <option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option>
                        </select>
                      </label>
                    </div>
                    <div className="stack" style={{border:"1px solid var(--border)",borderRadius:"0.75rem",padding:"0.75rem"}}>
                      <strong>Response SLA clock</strong>
                      {conversation.sla_paused_at ? <><span className="fine">Paused: {conversation.sla_pause_reason || "No reason recorded"}</span><button className="button secondary" type="button" disabled={!canManage || whatsappInboxBusy} onClick={()=>changeWhatsAppSLAPause(conversation,"resume")}>Resume SLA clock</button></> : <><input className="input" value={whatsappSLAPauseReason} maxLength={500} onChange={event=>setWhatsappSLAPauseReason(event.target.value)} placeholder="Reason for pausing the SLA clock"/><button className="button secondary" type="button" disabled={!canManage || whatsappInboxBusy || !whatsappSLAPauseReason.trim()} onClick={()=>changeWhatsAppSLAPause(conversation,"pause")}>Pause SLA clock</button></>}
                    </div>
                    <h4>Internal notes</h4>
                    {whatsappNotes.length ? <ul>{whatsappNotes.map(note=><li key={note.id} style={{marginBottom:"0.5rem"}}><p>{note.body}</p><span className="fine">{members.find(member=>member.user_id===note.author_user_id)?.email || "Workspace teammate"} · {new Date(note.created_at).toLocaleString()}</span></li>)}</ul> : <p className="fine">No internal notes yet.</p>}
                    <textarea className="input" rows={3} maxLength={5000} value={whatsappNoteDraft} onChange={event=>setWhatsappNoteDraft(event.target.value)} placeholder="Add an internal note for your team (not sent to the contact)" />
                    <button className="button secondary" type="button" disabled={whatsappInboxBusy || !whatsappNoteDraft.trim()} onClick={addWhatsAppInternalNote}>Add internal note</button>
                  </div>;
                })()}
                <h4>Activity history</h4>
                {whatsappActivity.length ? <ol>{whatsappActivity.map(event => <li key={event.id} style={{marginBottom:"0.4rem"}}>
                  <span>{event.event_type.replace(/_/g," ")}</span>
                  <div className="fine">{members.find(member=>member.user_id===event.actor_user_id)?.email || "Workspace teammate"} · {new Date(event.created_at).toLocaleString()}</div>
                </li>)}</ol> : <p className="fine">No activity recorded yet.</p>}
                <h4>Messages</h4>
                {selectedWhatsAppConversation ? (whatsappMessages.length ? <ol>
                  {whatsappMessages.map(message => <li key={message.id} style={{marginBottom:"0.75rem"}}>
                    <p>{message.text_body || ("[" + message.message_type + " message]")}</p>
                    {message.media_metadata && Object.keys(message.media_metadata).length > 0 && <pre className="fine" style={{whiteSpace:"pre-wrap"}}>{JSON.stringify(message.media_metadata, null, 2)}</pre>}
                    {message.media_metadata && typeof message.media_metadata.id === "string" && ["image","video","audio","document","sticker"].includes(message.message_type) && <div>
                      <button className="button secondary" type="button" disabled={whatsappInboxBusy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={() => downloadWhatsAppMedia(message)}>{message.media_downloaded_at ? "Download again / refresh stored attachment" : "Secure attachment download"}</button>
                      {message.media_downloaded_at && <><span className="fine">Stored: {message.media_filename || "attachment"} · {message.media_size || 0} bytes</span>{" "}<button className="button secondary" type="button" disabled={whatsappInboxBusy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={() => deleteWhatsAppMedia(message)}>Delete stored attachment</button></>}{" "}<a href={"/api/v1/integrations/whatsapp/inbox/messages/" + encodeURIComponent(message.id) + "/media?workspace_id=" + encodeURIComponent(workspaceId)} target="_blank" rel="noreferrer">Open stored attachment</a>
                    </div>}
                    <p className="fine">{message.provider_timestamp ? new Date(message.provider_timestamp).toLocaleString() : new Date(message.received_at).toLocaleString()}</p>
                  </li>)}
                </ol> : <p className="fine">No messages in this conversation.</p>) : <p className="fine">Select a conversation to view its inbound messages.</p>}
                <button className="button secondary" type="button" disabled={whatsappInboxBusy || !workspaceId || !csrf} onClick={() => refresh(workspaceId, csrf)}>Refresh inbox</button>
              </article>
            </div>
            {["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <details className="card"><summary>Register Meta WhatsApp account</summary>
              <form onSubmit={createWhatsAppAccount}>
                <div className="field"><label htmlFor="whatsapp-account-label">Account label</label><input id="whatsapp-account-label" required maxLength={120} value={whatsappLabel} onChange={e=>setWhatsappLabel(e.target.value)} /></div>
                <div className="field"><label htmlFor="whatsapp-waba-id">WhatsApp Business Account ID</label><input id="whatsapp-waba-id" inputMode="numeric" required minLength={5} maxLength={128} value={whatsappWabaId} onChange={e=>setWhatsappWabaId(e.target.value)} /></div>
                <div className="field"><label htmlFor="whatsapp-phone-id">Phone number ID</label><input id="whatsapp-phone-id" inputMode="numeric" required minLength={5} maxLength={128} value={whatsappPhoneNumberId} onChange={e=>setWhatsappPhoneNumberId(e.target.value)} /></div>
                <div className="field"><label htmlFor="whatsapp-access-token">Meta access token</label><input id="whatsapp-access-token" type="password" autoComplete="new-password" required minLength={20} maxLength={4096} value={whatsappAccessToken} onChange={e=>setWhatsappAccessToken(e.target.value)} /></div>
                <button className="button" type="submit" disabled={busy || !workspaceId || !csrf}>Encrypt and save (pending verification)</button>
              </form>
            </details>}
            <p className="fine">Inbound Meta webhook signatures are validated and events are stored in a private inbox. A worker can map events to workspace-owned accounts and persist inbound messages/statuses; configure a trusted scheduler to process the inbox. Outbound sending is off by default; dispatch re-checks opt-in, template/window policy, subscription quota and account status.</p>
          </article>
        </section>

        <section className="section" id="inbox" aria-labelledby="unified-reply-inbox-title">
          <h2 id="unified-reply-inbox-title">Unified reply inbox</h2>
          <p className="fine">Inbound and outbound email and WhatsApp messages linked to workspace CRM prospects appear together. Replies are created as drafts and require approval before delivery.</p>
          <div className="cards">
            <article className="card">
              <h3>Reply threads ({unifiedReplyThreads.length})</h3>
              {unifiedReplyThreads.length ? unifiedReplyThreads.map(thread=><button key={thread.prospect_id} type="button" className={"button " + (selectedReplyProspectId===thread.prospect_id ? "" : "secondary")} disabled={unifiedReplyBusy} onClick={()=>openUnifiedReplyThread(thread)} style={{display:"block",width:"100%",textAlign:"left",marginBottom:"0.5rem",whiteSpace:"normal"}}>
                <strong>{thread.prospect_name}</strong><span style={{display:"block"}}>{thread.prospect_company} · {thread.channel.toUpperCase()} · {thread.message_count} messages · {thread.latest_direction || "inbound"}{thread.latest_delivery_status ? " · " + thread.latest_delivery_status : ""}</span><span style={{display:"block"}}>{thread.latest_message}</span><span className="fine">{new Date(thread.latest_message_at).toLocaleString()}</span>
              </button>) : <p className="fine">No linked email or WhatsApp replies have been received yet.</p>}
              <button className="button secondary" type="button" disabled={busy || !workspaceId || !csrf} onClick={()=>refresh(workspaceId,csrf)}>Refresh reply inbox</button>
            </article>
            <article className="card">
              <h3>Conversation history</h3>
              {selectedReplyProspectId ? (unifiedReplyMessages.length ? <ol>{unifiedReplyMessages.map(message=><li key={message.id} style={{marginBottom:"0.75rem"}}><p>{message.body}</p><p className="fine">{message.direction} · {message.channel.toUpperCase()} · {message.provider}{message.delivery_status ? " · " + message.delivery_status : ""} · {new Date(message.occurred_at).toLocaleString()}</p></li>)}</ol> : <p className="fine">No messages are available for this prospect.</p>) : <p className="fine">Select a reply thread to view its complete inbound history.</p>}
              {selectedReplyProspectId && (() => {
                const thread = unifiedReplyThreads.find(item => item.prospect_id === selectedReplyProspectId);
                if (!thread) return null;
                return <form className="stack" onSubmit={event => { event.preventDefault(); void createUnifiedReplyDraft(); }}>
                  <h4>Create {thread.channel.toUpperCase()} reply draft</h4>
                  {thread.channel === "email" && <label>Subject<input required maxLength={300} value={replyDraftSubject} onChange={event=>setReplyDraftSubject(event.target.value)} /></label>}
                  <label>Reply<textarea required maxLength={10000} rows={5} value={replyDraftBody} onChange={event=>setReplyDraftBody(event.target.value)} placeholder="Write a reply for human approval..." /></label>
                  <button className="button" type="submit" disabled={unifiedReplyBusy || !replyDraftBody.trim()}>Create approval draft</button>
                  <p className="fine">This creates a pending-approval draft. Sending still requires normal approval, consent, provider and quota checks.</p>
                </form>;
              })()}
            </article>
          </div>
        </section>
        <section className="section" id="deliveries"><h2>Delivery activity</h2><p className="fine">A queued email is not sent until a workspace admin explicitly confirms. Unknown outcomes are not automatically retried.</p>{["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && deliveries.some(delivery=>delivery.status==="processing") && <div className="actions"><button className="button secondary" type="button" disabled={busy} onClick={reconcileStaleDeliveries}>Reconcile sends stuck for 15+ minutes</button><p className="fine">This only marks stale sends as uncertain. It never automatically retries messages.</p></div>}<div className="cards">{deliveries.length ? deliveries.map(delivery=><article className="card" key={delivery.id}><p className="eyebrow">{delivery.channel || "email"} · {delivery.status}</p><h3>{delivery.subject || "Email delivery"}</h3>{delivery.created_at && <p className="fine">Queued: {delivery.created_at}</p>}{delivery.scheduled_at && <p className="fine">Scheduled: {new Date(delivery.scheduled_at).toLocaleString()}</p>}{delivery.error_code && <p className="fine">Status detail: {delivery.error_code}</p>}{delivery.provider_status && <p className="fine">Email provider: {delivery.provider_status}{delivery.provider_status_at ? " · " + delivery.provider_status_at : ""}</p>}{delivery.status === "queued" && delivery.channel === "email" && <div className="actions">{new Date(delivery.scheduled_at || 0).getTime() <= Date.now() && <button className="button" type="button" disabled={busy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={() => sendDelivery(delivery)}>Send now</button>}<button className="button secondary" type="button" disabled={busy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") || !deliveryScheduleLocal} onClick={() => rescheduleDelivery(delivery)}>Reschedule</button><button className="button secondary" type="button" disabled={busy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={() => cancelDelivery(delivery)}>Cancel</button></div>}</article>) : <article className="card"><p>No delivery records yet. Approved email drafts can be queued above.</p></article>}</div></section>
        <section className="section" aria-labelledby="sessions-title">
          <h2 id="sessions-title">Signed-in devices and sessions</h2>
          <article className="card">
            <p>Review active sign-ins for this account. You can remotely sign out a device you no longer use; the current session is protected and must be ended with Sign out.</p>
            <div className="actions"><button className="button secondary" type="button" disabled={busy || !csrf} onClick={loadAuthSessions}>Refresh sessions</button><button className="button secondary" type="button" disabled={busy || !csrf || authSessions.filter(session=>!session.is_current).length===0} onClick={revokeOtherAuthSessions}>Sign out all other devices</button></div>
            <div className="cards">{authSessions.length ? authSessions.map(session=><article className="card" key={session.id}>
              <h3>{session.is_current ? "This device (current session)" : "Other signed-in device"}</h3>
              <p className="fine">Last active: {new Date(session.last_seen_at).toLocaleString()} · Expires: {new Date(session.expires_at).toLocaleString()}</p>
              {session.user_agent && <p className="fine">{session.user_agent}</p>}
              {!session.is_current && <button className="button secondary" type="button" disabled={busy} onClick={()=>revokeAuthSession(session)}>Sign out this device</button>}
            </article>) : <article className="card"><p>No active sessions loaded. Refresh to retrieve this account's signed-in devices.</p></article>}</div>
          </article>
        </section>
        <section className="section" aria-labelledby="account-danger-title">
          <h2 id="account-danger-title">Account privacy and deletion</h2>
          <article className="card">
            <h3>Export or delete your account</h3>
            <p>Your account export is available from the footer. Deletion revokes sessions and pending invitations, consumes outstanding verification/reset tokens, and pseudonymizes your login identity. Sole-member workspaces are removed; shared workspaces are retained for other non-revoked members. Security audit history remains with a pseudonymized identity; local billing rows for a deleted sole-member workspace are removed with that workspace. External provider records and backups follow separate retention controls.</p>
            <button className="button secondary" type="button" disabled={busy || !csrf} onClick={deleteAccount}>Delete my account</button>
            <p className="fine">This action is irreversible and requires two explicit confirmations. It does not claim to erase records retained by external providers or legally required operational records.</p>
          </article>
        </section>
      </>}
    </main>
    <footer className="wrap"><p>Private workspace · <Link href="/privacy">Privacy</Link> · <Link href="/terms">Terms</Link> · <Link href="/contact">Contact</Link> · <a href="/api/v1/account/export">Download account data (JSON)</a> · <Link href="/">Public site</Link></p></footer>
  </>;
}
