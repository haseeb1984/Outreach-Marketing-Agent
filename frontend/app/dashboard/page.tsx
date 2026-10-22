"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type Workspace = { id: string; name: string; role: string };
type Prospect = { id: string; name: string; company: string; role?: string | null; contact_email?: string | null; website_url: string; evidence_url: string; fit_reason: string; stage: string; email_suppressed?: boolean; whatsapp_opt_in_documented?: boolean };
type Campaign = { id: string; name: string; client_business: string; target_customer_profile: string; status?: string };
type Draft = { id: string; subject?: string; body?: string; channel?: string; status: string; prospect_name?: string };
type Plan = { id: string; name: string; description: string; display_price: string | null; currency: string | null; billing_interval: string | null; checkout_available: boolean };
type Delivery = { id: string; subject?: string; channel?: string; status: string; error_code?: string | null; created_at?: string };
type Counts = Record<string, number>;
type Project = { id: string; name: string; website_url?: string | null; business_model: string; target_market: string; language: string; audience: string; offer: string; conversion_goal: string; brand_voice: string; competitors: string[]; status: string };
type Invitation = { id: string; invited_email: string; role: string; status: string; expires_at: string; accepted_at?: string | null; revoked_at?: string | null };
type WorkspaceMember = { user_id: string; email: string; role: string; status: string; created_at: string };
type Entitlement = { feature: string; allowed: boolean; reason: string; remaining: number | null };
type ResearchResult = { title: string; url: string; description: string; evidence_type: string; requires_human_review: boolean };
type DomainChallenge = { domain: string; expires_at: string; dns_record: { record_name: string; record_value: string; type: string }; instructions: string };
type AuditFinding = { code: string; title: string; severity: string; occurrences: number; evidence_urls: string[] };
type WebsiteAudit = { report: { start_url: string; crawl_skipped: boolean; reason?: string; robots?: { status?: string; url?: string; error?: string }; crawl?: { pages_crawled: number; aggregate_findings: AuditFinding[]; pages: Array<{ final_url: string; title?: string | null; status_code: number; findings: Array<{ code: string; title: string; severity: string }> }> }; limitations?: string[] }; notice: string };
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
      authentication_not_configured: "The account service is not configured.",
      campaign_service_not_configured: "Campaign service is not available yet.",
      prospect_service_not_configured: "Prospect service is not available yet.",
      analytics_service_not_configured: "Analytics service is not available yet.",
      billing_service_not_configured: "Billing service is not available yet.",
      csrf_validation_failed: "Security check failed. Refresh the page and try again.",
      request_origin_rejected: "The frontend origin is not yet authorized by the backend.",
      email_provider_not_configured: "Email sending is not configured.",
      quota_exhausted: "This workspace has reached its current usage limit.",
      search_provider_not_configured: "Live public-web research is not configured on the server yet.",
      search_provider_unavailable: "The search provider is temporarily unavailable. Try again later.",
      search_response_invalid: "The search provider returned an unexpected response.",
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
  const [prospects, setProspects] = useState<Prospect[]>([]);
  const [researchQuery, setResearchQuery] = useState("");
  const [researchResults, setResearchResults] = useState<ResearchResult[]>([]);
  const [researchBusy, setResearchBusy] = useState(false);
  const [domainName, setDomainName] = useState("");
  const [domainChallenge, setDomainChallenge] = useState<DomainChallenge | null>(null);
  const [domainBusy, setDomainBusy] = useState(false);
  const [auditUrl, setAuditUrl] = useState("");
  const [auditReport, setAuditReport] = useState<WebsiteAudit | null>(null);
  const [auditBusy, setAuditBusy] = useState(false);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [integrationStatus, setIntegrationStatus] = useState<{ email?: { configuration_complete: boolean; missing_fields: string[]; connection_tested?: boolean }; whatsapp?: { configuration_complete: boolean; missing_fields: string[]; live_send_enabled: boolean; reason?: string } } | null>(null);
  const [integrationBusy, setIntegrationBusy] = useState(false);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [selectedPlan, setSelectedPlan] = useState("");
  const [counts, setCounts] = useState<Counts>({});
  const [entitlements, setEntitlements] = useState<Entitlement[]>([]);
  const [entitlementsUnavailable, setEntitlementsUnavailable] = useState(false);
  const [period, setPeriod] = useState("30");
  const [loading, setLoading] = useState(true);
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
  const [prospectName, setProspectName] = useState("");
  const [prospectCompany, setProspectCompany] = useState("");
  const [prospectEmail, setProspectEmail] = useState("");
  const [prospectWebsite, setProspectWebsite] = useState("");
  const [evidenceUrl, setEvidenceUrl] = useState("");
  const [fitReason, setFitReason] = useState("");

  const loadWorkspaceData = useCallback(async (selectedId: string, token: string) => {
    if (!selectedId) return;
    const [p, c, d, a, deliveryResult] = await Promise.all([
      api<ApiResult<Prospect>>("/api/v1/prospects?workspace_id=" + encodeURIComponent(selectedId) + "&limit=50", token),
      api<ApiResult<Campaign>>("/api/v1/campaigns?workspace_id=" + encodeURIComponent(selectedId) + "&limit=50", token),
      api<ApiResult<Draft>>("/api/v1/drafts?workspace_id=" + encodeURIComponent(selectedId) + "&status=all&limit=50", token),
      api<{ counts: Counts }>("/api/v1/analytics/summary?workspace_id=" + encodeURIComponent(selectedId) + "&since_days=" + period, token),
      api<ApiResult<Delivery>>("/api/v1/deliveries?workspace_id=" + encodeURIComponent(selectedId) + "&limit=50", token),
    ]);
    setProspects(p.items || []);
    setCampaigns(c.items || []);
    setDrafts(d.items || []);
    setDeliveries(deliveryResult.items || []);
    setCounts(a.counts || {});
    const projectResult = await Promise.allSettled([
      api<ApiResult<Project>>("/api/v1/projects?workspace_id=" + encodeURIComponent(selectedId) + "&limit=50", token),
    ]);
    const projectResponse = projectResult[0];
    setProjects(projectResponse.status === "fulfilled" ? (projectResponse.value.items || []) : []);
    const invitationResult = await Promise.allSettled([api<{ items: Invitation[] }>("/api/v1/workspaces/invitations?workspace_id=" + encodeURIComponent(selectedId), token)]);
    setInvitations(invitationResult[0].status === "fulfilled" ? (invitationResult[0].value.items || []) : []);
    const memberResult = await Promise.allSettled([api<{ items: WorkspaceMember[] }>("/api/v1/workspaces/members?workspace_id=" + encodeURIComponent(selectedId), token)]);
    setMembers(memberResult[0].status === "fulfilled" ? (memberResult[0].value.items || []) : []);
    const entitlementResults = await Promise.allSettled([
      api<Entitlement>("/api/v1/billing/entitlements?workspace_id=" + encodeURIComponent(selectedId) + "&feature=ai_draft_generations", token),
      api<Entitlement>("/api/v1/billing/entitlements?workspace_id=" + encodeURIComponent(selectedId) + "&feature=email_sends", token),
    ]);
    const availableEntitlements = entitlementResults
      .filter((result): result is PromiseFulfilledResult<Entitlement> => result.status === "fulfilled")
      .map(result => result.value);
    setEntitlements(availableEntitlements);
    setEntitlementsUnavailable(availableEntitlements.length !== 2);
  }, [period]);

  const refresh = useCallback(async (selectedId = workspaceId, token = csrf) => {
    if (!selectedId || !token) return;
    setError("");
    try {
      await loadWorkspaceData(selectedId, token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Workspace data could not be loaded.");
    }
  }, [csrf, loadWorkspaceData, workspaceId]);

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
        const first = result.items?.[0]?.id || "";
        setWorkspaceId(first);
        if (first) await loadWorkspaceData(first, session.csrf_token);
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
    return () => { cancelled = true; };
  }, [loadWorkspaceData, router]);

  async function changeMemberRole(member: WorkspaceMember, role: string) {
    if (!workspaceId || !csrf || role === member.role) return;
    if (!window.confirm("Change " + member.email + "'s role to " + role + "?")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/workspaces/members/" + encodeURIComponent(member.user_id), csrf, {
        method: "PATCH", body: JSON.stringify({ workspace_id: workspaceId, role }),
      });
      setNotice("Workspace member role updated.");
      await refresh(workspaceId, csrf);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Member role could not be changed.");
      await refresh(workspaceId, csrf);
    } finally { setBusy(false); }
  }

  async function removeMember(member: WorkspaceMember) {
    if (!workspaceId || !csrf || !window.confirm("Remove " + member.email + " from this workspace? Their account will remain active.")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/workspaces/members/" + encodeURIComponent(member.user_id) + "?workspace_id=" + encodeURIComponent(workspaceId), csrf, { method: "DELETE" });
      setNotice("Member removed from this workspace.");
      await refresh(workspaceId, csrf);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Workspace member could not be removed.");
    } finally { setBusy(false); }
  }

  async function createInvitation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/workspaces/invitations", csrf, {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspaceId, email: inviteEmail, role: inviteRole }),
      });
      setInviteEmail("");
      setNotice("Invitation email sent. The recipient must sign in with that email address to accept.");
      await refresh(workspaceId, csrf);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Workspace invitation could not be sent.");
    } finally { setBusy(false); }
  }

  async function revokeInvitation(invitation: Invitation) {
    if (!workspaceId || !csrf || !window.confirm("Revoke the pending invitation for " + invitation.invited_email + "?")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/workspaces/invitations/" + encodeURIComponent(invitation.id) + "?workspace_id=" + encodeURIComponent(workspaceId), csrf, { method: "DELETE" });
      setNotice("Pending invitation revoked.");
      await refresh(workspaceId, csrf);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invitation could not be revoked.");
    } finally { setBusy(false); }
  }

  async function updateProject(event: FormEvent<HTMLFormElement>, project: Project) {
    event.preventDefault();
    if (!workspaceId || !csrf) return;
    const form = new FormData(event.currentTarget);
    const value = (key: string) => String(form.get(key) || "");
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/projects/" + encodeURIComponent(project.id), csrf, {
        method: "PATCH",
        body: JSON.stringify({
          workspace_id: workspaceId,
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
      setNotice("Project settings updated.");
      await refresh(workspaceId, csrf);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Project settings could not be updated.");
    } finally { setBusy(false); }
  }

  async function archiveProject(project: Project) {
    if (!workspaceId || !csrf || !["owner", "admin"].includes(workspaces.find(w => w.id === workspaceId)?.role || "")) return;
    if (!window.confirm("Archive project " + project.name + "? It will disappear from the active project list; existing workspace records are not deleted.")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/projects/" + encodeURIComponent(project.id) + "?workspace_id=" + encodeURIComponent(workspaceId), csrf, { method: "DELETE" });
      setNotice("Project archived. Its historical campaign and CRM records remain in the workspace.");
      await refresh(workspaceId, csrf);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Project could not be archived.");
    } finally { setBusy(false); }
  }

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const competitors = projectCompetitors.split(String.fromCharCode(10)).map(item => item.trim()).filter(Boolean).slice(0, 20);
      await api("/api/v1/projects", csrf, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspaceId, name: projectName, website_url: projectWebsite || null,
          business_model: projectBusinessModel, target_market: projectMarket, language: projectLanguage,
          audience: projectAudience, offer: projectOffer, conversion_goal: projectGoal,
          brand_voice: projectBrandVoice, competitors,
        }),
      });
      setProjectName(""); setProjectWebsite(""); setProjectBusinessModel(""); setProjectMarket("");
      setProjectLanguage(""); setProjectAudience(""); setProjectOffer(""); setProjectGoal("");
      setProjectBrandVoice(""); setProjectCompetitors("");
      setNotice("Project profile saved. Website ownership verification is a separate step.");
      await refresh(workspaceId, csrf);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Project could not be saved.");
    } finally { setBusy(false); }
  }

  async function createCampaign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/campaigns", csrf, { method: "POST", body: JSON.stringify({
        workspace_id: workspaceId, name: campaignName, client_business: businessName,
        client_offer: offer, target_customer_profile: targetProfile,
      }) });
      setCampaignName(""); setBusinessName(""); setOffer(""); setTargetProfile("");
      setNotice("Campaign created. No outreach has been sent.");
      await refresh(workspaceId, csrf);
    } catch (err) { setError(err instanceof Error ? err.message : "Campaign could not be created."); }
    finally { setBusy(false); }
  }

  async function createDomainChallenge(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf || !domainName.trim()) return;
    setDomainBusy(true); setError(""); setNotice(""); setDomainChallenge(null);
    try {
      const result = await api<DomainChallenge>("/api/v1/domains/challenges", csrf, {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspaceId, domain: domainName.trim() }),
      });
      setDomainChallenge(result);
      setNotice("DNS record created. Publish the record exactly as shown, then verify it.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Domain challenge could not be created.");
    } finally { setDomainBusy(false); }
  }

  async function verifyDomain() {
    if (!workspaceId || !csrf || !domainChallenge) return;
    setDomainBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/domains/verify", csrf, {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspaceId, domain: domainChallenge.domain }),
      });
      setAuditUrl("https://" + domainChallenge.domain + "/");
      setDomainChallenge(null);
      setNotice("Domain verified. Run a bounded read-only audit on the verified host.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Domain verification could not be completed.");
    } finally { setDomainBusy(false); }
  }

  async function runWebsiteAudit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf || !auditUrl.trim()) return;
    setAuditBusy(true); setError(""); setNotice(""); setAuditReport(null);
    try {
      const result = await api<WebsiteAudit>("/api/v1/website-audits", csrf, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspaceId,
          start_url: auditUrl.trim(),
          max_pages: 5,
          idempotency_key: "site-audit-" + crypto.randomUUID(),
        }),
      });
      setAuditReport(result);
      setNotice(result.notice || "Read-only audit completed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Website audit could not be completed.");
    } finally { setAuditBusy(false); }
  }

  async function searchProspects(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf || !researchQuery.trim()) return;
    setResearchBusy(true); setError(""); setNotice(""); setResearchResults([]);
    try {
      const result = await api<{ items: ResearchResult[]; notice?: string }>("/api/v1/research/prospects/search", csrf, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspaceId,
          query: researchQuery.trim(),
          count: 10,
          idempotency_key: "research-" + crypto.randomUUID(),
        }),
      });
      setResearchResults(result.items || []);
      setNotice(result.notice || "Research results loaded for human review.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Public-web research could not be completed.");
    } finally { setResearchBusy(false); }
  }

  async function createProspect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/prospects", csrf, { method: "POST", body: JSON.stringify({
        workspace_id: workspaceId, name: prospectName, company: prospectCompany,
        contact_email: prospectEmail || null, website_url: prospectWebsite,
        evidence_url: evidenceUrl, fit_reason: fitReason, verified_facts: [],
      }) });
      setProspectName(""); setProspectCompany(""); setProspectEmail(""); setProspectWebsite(""); setEvidenceUrl(""); setFitReason("");
      setNotice("Prospect saved with its evidence URL.");
      await refresh(workspaceId, csrf);
    } catch (err) { setError(err instanceof Error ? err.message : "Prospect could not be saved."); }
    finally { setBusy(false); }
  }

  async function setEmailSuppression(prospect: Prospect, suppressed: boolean) {
    if (!workspaceId || !csrf || !["owner", "admin"].includes(workspaces.find(w => w.id === workspaceId)?.role || "")) return;
    const action = suppressed ? "suppress future email outreach to" : "allow email outreach to";
    if (!window.confirm("Confirm you want to " + action + " " + prospect.name + "? Existing queued messages will still be rechecked before sending.")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/prospects/" + encodeURIComponent(prospect.id) + "/contact-controls", csrf, {
        method: "PUT",
        body: JSON.stringify({ workspace_id: workspaceId, email_suppressed: suppressed, whatsapp_opt_in_confirmed: false }),
      });
      setNotice(suppressed ? "Email suppression saved. Future draft, queue and send checks will honor it." : "Email suppression removed by an authorized workspace admin.");
      await refresh(workspaceId, csrf);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Contact controls could not be updated.");
    } finally { setBusy(false); }
  }

  async function generateDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !csrf || !selectedCampaign || !selectedProspect) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/drafts", csrf, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspaceId,
          campaign_id: selectedCampaign,
          prospect_id: selectedProspect,
          channel: draftChannel,
          call_to_action: draftCallToAction,
          idempotency_key: "draft-" + crypto.randomUUID(),
        }),
      });
      setDraftCallToAction("");
      setNotice("Draft created and placed in the review queue. Nothing was sent.");
      await refresh(workspaceId, csrf);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Draft could not be generated.");
    } finally { setBusy(false); }
  }

  async function queueDraft(draft: Draft) {
    if (!workspaceId || !csrf || !window.confirm("Queue this approved email draft? This does not send the email.")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/drafts/" + encodeURIComponent(draft.id) + "/enqueue", csrf, {
        method: "POST", body: JSON.stringify({ workspace_id: workspaceId, idempotency_key: "queue-" + crypto.randomUUID() }),
      });
      setNotice("Draft queued. It will not be sent until an authorized admin confirms Send now.");
      await refresh(workspaceId, csrf);
    } catch (err) { setError(err instanceof Error ? err.message : "Draft could not be queued."); }
    finally { setBusy(false); }
  }

  async function sendDelivery(delivery: Delivery) {
    if (!workspaceId || !csrf || !window.confirm("Send this queued email to the saved recipient now? This contacts a real person and cannot be undone.")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/deliveries/" + encodeURIComponent(delivery.id) + "/send", csrf, {
        method: "POST", body: JSON.stringify({ workspace_id: workspaceId, idempotency_key: "send-" + delivery.id }),
      });
      setNotice("Send request processed. SMTP acceptance is not proof of inbox delivery.");
      await refresh(workspaceId, csrf);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Send outcome could not be confirmed. Check delivery status before retrying.");
      await refresh(workspaceId, csrf);
    } finally { setBusy(false); }
  }

  async function reviewDraft(draft: Draft, decision: "approved" | "rejected") {
    if (!workspaceId || !csrf || !window.confirm("Confirm " + decision + " for this draft? This does not send a message.")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/drafts/" + encodeURIComponent(draft.id) + "/review", csrf, {
        method: "POST", body: JSON.stringify({ workspace_id: workspaceId, decision }),
      });
      setNotice("Draft " + decision + ". No message was sent.");
      await refresh(workspaceId, csrf);
    } catch (err) { setError(err instanceof Error ? err.message : "Draft review failed."); }
    finally { setBusy(false); }
  }

  async function startCheckout() {
    if (!workspaceId || !csrf || !selectedPlan) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<{ checkout_url: string }>("/api/v1/billing/paddle/checkout", csrf, {
        method: "POST", body: JSON.stringify({ workspace_id: workspaceId, plan_id: selectedPlan }),
      });
      const checkoutUrl = new URL(result.checkout_url);
      if (checkoutUrl.protocol !== "https:") throw new Error("The billing provider returned an unsafe checkout URL.");
      window.location.assign(checkoutUrl.toString());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout could not be started.");
    } finally { setBusy(false); }
  }

  async function refreshIntegrationStatus() {
    if (!workspaceId || !csrf) return;
    setIntegrationBusy(true);
    try {
      const result = await api<{ email: { configuration_complete: boolean; missing_fields: string[]; connection_tested?: boolean }; whatsapp: { configuration_complete: boolean; missing_fields: string[]; live_send_enabled: boolean; reason?: string } }>(
        "/api/v1/integrations/status?workspace_id=" + encodeURIComponent(workspaceId), csrf
      );
      setIntegrationStatus(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Provider status could not be loaded.");
    } finally { setIntegrationBusy(false); }
  }

  async function testSmtpConnection() {
    if (!workspaceId || !csrf || !window.confirm("Test the configured SMTP TLS connection and authentication? No email will be sent.")) return;
    setIntegrationBusy(true); setError(""); setNotice("");
    try {
      await api("/api/v1/integrations/smtp/test?workspace_id=" + encodeURIComponent(workspaceId), csrf, { method: "POST" });
      setNotice("SMTP TLS connection and authentication succeeded. No email was sent.");
      await refreshIntegrationStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "SMTP connection test failed.");
    } finally { setIntegrationBusy(false); }
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
    ["Marked sent", "emails_marked_sent"], ["Failed deliveries", "deliveries_failed"], ["Uncertain outcomes", "deliveries_uncertain"],
  ];

  return <>
    <header className="wrap topbar"><Link className="brand" href="/"><span className="mark" aria-hidden="true">O</span> Outreach Marketing Agent</Link><nav className="nav" aria-label="Workspace navigation"><Link href="/product">Product</Link><Link href="/pricing">Billing</Link><button className="button secondary" type="button" onClick={logout} disabled={busy}>Sign out</button></nav></header>
    <main className="wrap">
      <section className="page-head"><p className="eyebrow">Private workspace</p><h1>Your outreach workspace</h1><p className="lead">Signed in as {email || "your account"}. Research, campaigns and approvals stay separated by workspace.</p></section>
      <ErrorNotice message={error} />
      {notice && <p className="notice" role="status" aria-live="polite">{notice}</p>}
      {loading ? <section className="card" aria-live="polite">Loading secure workspace data…</section> : <>
        <section className="card" aria-labelledby="workspace-title"><div className="field"><label id="workspace-title" htmlFor="workspace">Active workspace</label><select id="workspace" value={workspaceId} onChange={async e => { const id=e.target.value; setWorkspaceId(id); await refresh(id, csrf); }}><option value="">Choose a workspace</option>{workspaces.map(w=><option key={w.id} value={w.id}>{w.name} · {w.role}</option>)}</select></div>
          {!workspaces.length && <p className="fine">No active workspace membership was returned for this account. Complete account/workspace onboarding before using campaign features.</p>}
          <div className="actions"><button className="button secondary" type="button" onClick={() => refresh()} disabled={busy || !workspaceId}>Refresh workspace</button><label className="fine" htmlFor="period">Analytics period</label><select id="period" value={period} onChange={async e => { setPeriod(e.target.value); }}><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option></select></div>
        </section>
        {["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <section className="section" aria-labelledby="invitations-title"><h2 id="invitations-title">Team invitations</h2>
          <article className="card"><p className="fine">Invite a teammate by email and assign the least-privileged role they need. Invitation links expire after seven days and can only be accepted by the invited email account.</p>
            <form onSubmit={createInvitation}><div className="field"><label htmlFor="invite-email">Teammate email</label><input id="invite-email" type="email" required maxLength={320} value={inviteEmail} onChange={e=>setInviteEmail(e.target.value)} /></div>
              <div className="field"><label htmlFor="invite-role">Workspace role</label><select id="invite-role" value={inviteRole} onChange={e=>setInviteRole(e.target.value)}><option value="viewer">Viewer — read-only</option><option value="member">Member — create and manage work</option><option value="admin">Admin — workspace administration</option></select></div>
              <button className="button" type="submit" disabled={busy || !workspaceId || !csrf}>Send invitation</button>
            </form>
          </article>
          <h3>Current members</h3>
          <div className="cards">{members.length ? members.map(member=><article className="card" key={member.user_id}><h3>{member.email}</h3><p className="fine">{member.status} · {member.role}</p>
            {member.role !== "owner" && <div className="field"><label htmlFor={"role-" + member.user_id}>Role</label><select id={"role-" + member.user_id} value={member.role} disabled={busy || (member.role === "admin" && workspaces.find(w=>w.id===workspaceId)?.role !== "owner")} onChange={e=>changeMemberRole(member,e.target.value)}><option value="viewer">Viewer</option><option value="member">Member</option><option value="admin" disabled={workspaces.find(w=>w.id===workspaceId)?.role !== "owner"}>Admin</option></select></div>}
            {member.role !== "owner" && <button className="button secondary" type="button" disabled={busy || (member.role === "admin" && workspaces.find(w=>w.id===workspaceId)?.role !== "owner")} onClick={()=>removeMember(member)}>Remove member</button>}
          </article>) : <article className="card"><p>Member list is unavailable or no active memberships were returned.</p></article>}</div>
          <div className="cards">{invitations.length ? invitations.map(invitation=><article className="card" key={invitation.id}><h3>{invitation.invited_email}</h3><p className="fine">Role: {invitation.role} · Status: {invitation.status}</p><p className="fine">Expires: {new Date(invitation.expires_at).toLocaleString()}</p>{invitation.status === "pending" && <button className="button secondary" type="button" disabled={busy} onClick={() => revokeInvitation(invitation)}>Revoke invitation</button>}</article>) : <article className="card"><p>No invitations available for this workspace, or the invitation service is not yet configured.</p></article>}</div>
        </section>}
        <section className="section" aria-labelledby="billing-title"><h2 id="billing-title">Plan and billing</h2>
          {plans.length ? <div className="cards">{plans.map(plan=><article className="card" key={plan.id}><h3>{plan.name}</h3><p>{plan.description || "Workspace subscription plan."}</p><p className="fine">{plan.display_price ? plan.display_price + (plan.currency ? " " + plan.currency : "") + (plan.billing_interval ? " / " + plan.billing_interval : "") : "Price is configured in the billing provider; display price has not been supplied."}</p><p className="fine">{plan.checkout_available ? "Provider configuration is present; complete sandbox and production verification before launch." : "Checkout is not enabled until server-side billing configuration is complete."}</p></article>)}</div> : <article className="card"><p>No billing plans are configured yet. Plans must be configured server-side; this screen never invents prices.</p></article>}
          {plans.some(plan=>plan.checkout_available) && <div className="card"><div className="field"><label htmlFor="billing-plan">Choose a plan</label><select id="billing-plan" value={selectedPlan} onChange={e=>setSelectedPlan(e.target.value)}>{plans.filter(plan=>plan.checkout_available).map(plan=><option key={plan.id} value={plan.id}>{plan.name}</option>)}</select></div><button className="button" type="button" disabled={busy || !workspaceId || !selectedPlan || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={startCheckout}>Continue to secure checkout</button><p className="fine">Workspace owner/admin permission is required. Paid access activates only after a verified billing webhook updates server-side subscription state.</p></div>}
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
        <section className="section" aria-labelledby="metrics-title"><div className="section-head"><h2 id="metrics-title">Recorded activity</h2><p className="fine">Counts from saved records; not estimates of revenue or ROI.</p></div><div className="dashboard-grid">{metricItems.map(([label,key])=><article className="metric" key={key}><strong>{counts[key] ?? "—"}</strong><span>{label}</span></article>)}</div><p className="fine">“Marked sent” means the configured email adapter returned successfully; it does not prove inbox delivery. Clicks, revenue and ROI are not inferred.</p></section>
        <section className="section"><div className="cards">
          <article className="card"><h2>Create campaign</h2><p className="fine">Define the offer and intended audience before generating any draft.</p><form onSubmit={createCampaign}><div className="field"><label htmlFor="campaign-name">Campaign name</label><input id="campaign-name" required maxLength={200} value={campaignName} onChange={e=>setCampaignName(e.target.value)} /></div><div className="field"><label htmlFor="business-name">Business / client</label><input id="business-name" required maxLength={240} value={businessName} onChange={e=>setBusinessName(e.target.value)} /></div><div className="field"><label htmlFor="offer">Offer</label><textarea id="offer" required maxLength={2000} value={offer} onChange={e=>setOffer(e.target.value)} /></div><div className="field"><label htmlFor="target-profile">Target customer profile</label><textarea id="target-profile" required maxLength={2000} value={targetProfile} onChange={e=>setTargetProfile(e.target.value)} /></div><button className="button" disabled={busy || !canWrite || !workspaceId}>Create campaign</button></form></article>
          <article className="card"><h2>Add a prospect</h2><p className="fine">Save public evidence and a clear reason for fit. Website and evidence URLs must use HTTPS.</p><form onSubmit={createProspect}><div className="field"><label htmlFor="prospect-name">Contact / prospect name</label><input id="prospect-name" required maxLength={200} value={prospectName} onChange={e=>setProspectName(e.target.value)} /></div><div className="field"><label htmlFor="prospect-company">Company</label><input id="prospect-company" required maxLength={240} value={prospectCompany} onChange={e=>setProspectCompany(e.target.value)} /></div><div className="field"><label htmlFor="prospect-email">Business email (optional)</label><input id="prospect-email" type="email" maxLength={320} value={prospectEmail} onChange={e=>setProspectEmail(e.target.value)} /></div><div className="field"><label htmlFor="prospect-website">Website URL</label><input id="prospect-website" type="url" required placeholder="https://example.com" value={prospectWebsite} onChange={e=>setProspectWebsite(e.target.value)} /></div><div className="field"><label htmlFor="evidence-url">Evidence URL</label><input id="evidence-url" type="url" required placeholder="https://example.com/about" value={evidenceUrl} onChange={e=>setEvidenceUrl(e.target.value)} /></div><div className="field"><label htmlFor="fit-reason">Why this prospect fits</label><textarea id="fit-reason" required maxLength={2000} value={fitReason} onChange={e=>setFitReason(e.target.value)} /></div><button className="button" disabled={busy || !canWrite || !workspaceId}>Save prospect</button></form></article>
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
            {["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <button className="button secondary" type="button" disabled={busy} onClick={() => archiveProject(project)}>Archive project</button>}</article>) : <article className="card"><p>No project profiles yet. Create one for each website or client business.</p></article>}</div>
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
        <section className="section"><h2>Campaigns</h2><div className="cards">{campaigns.length ? campaigns.map(c=><article className="card" key={c.id}><h3>{c.name}</h3><p>{c.client_business}</p><p className="fine">{c.target_customer_profile}</p><span className="fine">{c.status || "Saved campaign"}</span></article>) : <article className="card"><p>No campaigns yet. Create one above to organize outreach.</p></article>}</div></section>
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
          {researchResults.length > 0 && <div className="cards">{researchResults.map(item=><article className="card" key={item.url}><h3><a href={item.url} target="_blank" rel="noreferrer">{item.title}</a></h3><p>{item.description || "No search description supplied."}</p><p className="fine">Evidence: public search result · Review required · Not saved to CRM</p></article>)}</div>}
        </section>
        <section className="section"><h2>Prospect CRM</h2><div className="cards">{prospects.length ? prospects.map(p=><article className="card" key={p.id}><h3>{p.name}</h3><p>{p.role ? p.role + " · " : ""}{p.company}</p><p>{p.fit_reason}</p><p className="fine">Stage: {p.stage || "new"}{p.contact_email ? " · " + p.contact_email : ""}</p>{p.contact_email && <p className="fine">Email outreach: {p.email_suppressed ? "Suppressed" : "Not suppressed"}</p>}<p><a href={p.evidence_url} target="_blank" rel="noreferrer">Open evidence source</a></p>{p.contact_email && ["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "") && <div className="actions"><button className="button secondary" type="button" disabled={busy} onClick={() => setEmailSuppression(p, !p.email_suppressed)}>{p.email_suppressed ? "Allow email outreach" : "Suppress email outreach"}</button></div>}</article>) : <article className="card"><p>No prospects saved yet.</p></article>}</div></section>
        <section className="section"><h2>Prepare an outreach draft</h2><article className="card"><p className="fine">Draft generation uses workspace entitlements and saved prospect evidence. Every draft enters review; this form never sends a message.</p><form onSubmit={generateDraft}><div className="field"><label htmlFor="draft-campaign">Campaign</label><select id="draft-campaign" required value={selectedCampaign} onChange={e=>setSelectedCampaign(e.target.value)}><option value="">Choose a campaign</option>{campaigns.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></div><div className="field"><label htmlFor="draft-prospect">Prospect</label><select id="draft-prospect" required value={selectedProspect} onChange={e=>setSelectedProspect(e.target.value)}><option value="">Choose a prospect</option>{prospects.map(p=><option key={p.id} value={p.id}>{p.name} · {p.company}</option>)}</select></div><div className="field"><label htmlFor="draft-channel">Channel</label><select id="draft-channel" value={draftChannel} onChange={e=>setDraftChannel(e.target.value)}><option value="email">Email</option><option value="whatsapp">WhatsApp draft (eligibility checked by backend)</option></select></div><div className="field"><label htmlFor="draft-cta">Call to action</label><textarea id="draft-cta" required maxLength={500} value={draftCallToAction} onChange={e=>setDraftCallToAction(e.target.value)} placeholder="Suggest a short, relevant next step" /></div><button className="button" disabled={busy || !canWrite || !workspaceId || !campaigns.length || !prospects.length}>Generate draft for review</button></form></article></section>
        <section className="section"><h2>Draft review queue</h2><p className="fine">Approving a draft does not send it. Sending remains a separate explicit action.</p><div className="cards">{drafts.length ? drafts.map(d=><article className="card" key={d.id}><p className="eyebrow">{d.channel || "Outreach"} · {d.status}</p><h3>{d.subject || d.prospect_name || "Outreach draft"}</h3><p>{d.body || "Draft content is not available."}</p>{d.status === "approved" && d.channel === "email" && <div className="actions"><button type="button" className="button secondary" disabled={busy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={() => queueDraft(d)}>Queue email</button></div>}{d.status === "pending_approval" && <div className="actions"><button type="button" className="button" disabled={busy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={() => reviewDraft(d,"approved")}>Approve draft</button><button type="button" className="button secondary" disabled={busy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={() => reviewDraft(d,"rejected")}>Reject</button></div>}</article>) : <article className="card"><p>No drafts yet. Draft generation requires configured paid entitlements and eligible prospect evidence.</p></article>}</div></section>
        <section className="section" aria-labelledby="integrations-title"><h2 id="integrations-title">Provider connections</h2>
          <article className="card">
            <p className="fine">Current email support uses deployment-level SMTP settings. It does not yet connect multiple personal mailboxes per workspace. Provider diagnostics never return credentials.</p>
            <div className="actions">
              <button className="button secondary" type="button" onClick={refreshIntegrationStatus} disabled={integrationBusy || !workspaceId || !csrf}>Refresh status</button>
              <button className="button" type="button" onClick={testSmtpConnection} disabled={integrationBusy || !workspaceId || !csrf || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")}>Test SMTP (no email sent)</button>
            </div>
            {integrationStatus ? <div className="cards">
              <div className="metric"><strong>{integrationStatus.email?.configuration_complete ? "Configured" : "Incomplete"}</strong><span>Email / SMTP</span><p className="fine">{integrationStatus.email?.configuration_complete ? "Required settings are present; use the test button to verify TLS/authentication." : "Missing: " + (integrationStatus.email?.missing_fields || []).join(", ")}</p></div>
              <div className="metric"><strong>{integrationStatus.whatsapp?.live_send_enabled ? "Enabled" : "Disabled"}</strong><span>Official WhatsApp Business</span><p className="fine">{integrationStatus.whatsapp?.reason || "Live sending remains disabled until official Meta onboarding and webhook verification are implemented."}</p></div>
            </div> : <p className="fine">Provider status has not been loaded for this workspace.</p>}
            <p className="fine">This release does not claim multiple connected email accounts or active WhatsApp sending. WhatsApp stays disabled until official Meta onboarding, signature verification, tenant-scoped credentials, and inbound event persistence are implemented.</p>
          </article>
        </section>
        <section className="section"><h2>Delivery activity</h2><p className="fine">A queued email is not sent until a workspace admin explicitly confirms. Unknown outcomes are not automatically retried.</p><div className="cards">{deliveries.length ? deliveries.map(delivery=><article className="card" key={delivery.id}><p className="eyebrow">{delivery.channel || "email"} · {delivery.status}</p><h3>{delivery.subject || "Email delivery"}</h3>{delivery.created_at && <p className="fine">Queued: {delivery.created_at}</p>}{delivery.error_code && <p className="fine">Status detail: {delivery.error_code}</p>}{delivery.status === "queued" && delivery.channel === "email" && <button className="button" type="button" disabled={busy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={() => sendDelivery(delivery)}>Send now</button>}</article>) : <article className="card"><p>No delivery records yet. Approved email drafts can be queued above.</p></article>}</div></section>
      </>}
    </main>
    <footer className="wrap"><p>Private workspace · <Link href="/privacy">Privacy</Link> · <Link href="/terms">Terms</Link> · <a href="/api/v1/account/export">Download account data (JSON)</a> · <Link href="/">Public site</Link></p></footer>
  </>;
}
