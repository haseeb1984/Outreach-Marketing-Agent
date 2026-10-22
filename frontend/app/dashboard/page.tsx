"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type Workspace = { id: string; name: string; role: string };
type Prospect = { id: string; name: string; company: string; role?: string | null; contact_email?: string | null; website_url: string; evidence_url: string; fit_reason: string; stage: string };
type Campaign = { id: string; name: string; client_business: string; target_customer_profile: string; status?: string };
type Draft = { id: string; subject?: string; body?: string; channel?: string; status: string; prospect_name?: string };
type Counts = Record<string, number>;
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
  const [workspaceId, setWorkspaceId] = useState("");
  const [prospects, setProspects] = useState<Prospect[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [counts, setCounts] = useState<Counts>({});
  const [period, setPeriod] = useState("30");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [campaignName, setCampaignName] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [offer, setOffer] = useState("");
  const [targetProfile, setTargetProfile] = useState("");
  const [prospectName, setProspectName] = useState("");
  const [prospectCompany, setProspectCompany] = useState("");
  const [prospectEmail, setProspectEmail] = useState("");
  const [prospectWebsite, setProspectWebsite] = useState("");
  const [evidenceUrl, setEvidenceUrl] = useState("");
  const [fitReason, setFitReason] = useState("");

  const loadWorkspaceData = useCallback(async (selectedId: string, token: string) => {
    if (!selectedId) return;
    const [p, c, d, a] = await Promise.all([
      api<ApiResult<Prospect>>("/api/v1/prospects?workspace_id=" + encodeURIComponent(selectedId) + "&limit=50", token),
      api<ApiResult<Campaign>>("/api/v1/campaigns?workspace_id=" + encodeURIComponent(selectedId) + "&limit=50", token),
      api<ApiResult<Draft>>("/api/v1/drafts?workspace_id=" + encodeURIComponent(selectedId) + "&status=all&limit=50", token),
      api<{ counts: Counts }>("/api/v1/analytics/summary?workspace_id=" + encodeURIComponent(selectedId) + "&since_days=" + period, token),
    ]);
    setProspects(p.items || []);
    setCampaigns(c.items || []);
    setDrafts(d.items || []);
    setCounts(a.counts || {});
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
    ["Marked sent", "emails_marked_sent"], ["Failed or uncertain", "deliveries_failed"],
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
        <section className="section" aria-labelledby="metrics-title"><div className="section-head"><h2 id="metrics-title">Recorded activity</h2><p className="fine">Counts from saved records; not estimates of revenue or ROI.</p></div><div className="dashboard-grid">{metricItems.map(([label,key])=><article className="metric" key={key}><strong>{counts[key] ?? "—"}</strong><span>{label}</span></article>)}</div><p className="fine">“Marked sent” means the configured email adapter returned successfully; it does not prove inbox delivery. Clicks, revenue and ROI are not inferred.</p></section>
        <section className="section"><div className="cards">
          <article className="card"><h2>Create campaign</h2><p className="fine">Define the offer and intended audience before generating any draft.</p><form onSubmit={createCampaign}><div className="field"><label htmlFor="campaign-name">Campaign name</label><input id="campaign-name" required maxLength={200} value={campaignName} onChange={e=>setCampaignName(e.target.value)} /></div><div className="field"><label htmlFor="business-name">Business / client</label><input id="business-name" required maxLength={240} value={businessName} onChange={e=>setBusinessName(e.target.value)} /></div><div className="field"><label htmlFor="offer">Offer</label><textarea id="offer" required maxLength={2000} value={offer} onChange={e=>setOffer(e.target.value)} /></div><div className="field"><label htmlFor="target-profile">Target customer profile</label><textarea id="target-profile" required maxLength={2000} value={targetProfile} onChange={e=>setTargetProfile(e.target.value)} /></div><button className="button" disabled={busy || !canWrite || !workspaceId}>Create campaign</button></form></article>
          <article className="card"><h2>Add a prospect</h2><p className="fine">Save public evidence and a clear reason for fit. Website and evidence URLs must use HTTPS.</p><form onSubmit={createProspect}><div className="field"><label htmlFor="prospect-name">Contact / prospect name</label><input id="prospect-name" required maxLength={200} value={prospectName} onChange={e=>setProspectName(e.target.value)} /></div><div className="field"><label htmlFor="prospect-company">Company</label><input id="prospect-company" required maxLength={240} value={prospectCompany} onChange={e=>setProspectCompany(e.target.value)} /></div><div className="field"><label htmlFor="prospect-email">Business email (optional)</label><input id="prospect-email" type="email" maxLength={320} value={prospectEmail} onChange={e=>setProspectEmail(e.target.value)} /></div><div className="field"><label htmlFor="prospect-website">Website URL</label><input id="prospect-website" type="url" required placeholder="https://example.com" value={prospectWebsite} onChange={e=>setProspectWebsite(e.target.value)} /></div><div className="field"><label htmlFor="evidence-url">Evidence URL</label><input id="evidence-url" type="url" required placeholder="https://example.com/about" value={evidenceUrl} onChange={e=>setEvidenceUrl(e.target.value)} /></div><div className="field"><label htmlFor="fit-reason">Why this prospect fits</label><textarea id="fit-reason" required maxLength={2000} value={fitReason} onChange={e=>setFitReason(e.target.value)} /></div><button className="button" disabled={busy || !canWrite || !workspaceId}>Save prospect</button></form></article>
        </div></section>
        <section className="section"><h2>Campaigns</h2><div className="cards">{campaigns.length ? campaigns.map(c=><article className="card" key={c.id}><h3>{c.name}</h3><p>{c.client_business}</p><p className="fine">{c.target_customer_profile}</p><span className="fine">{c.status || "Saved campaign"}</span></article>) : <article className="card"><p>No campaigns yet. Create one above to organize outreach.</p></article>}</div></section>
        <section className="section"><h2>Prospect CRM</h2><div className="cards">{prospects.length ? prospects.map(p=><article className="card" key={p.id}><h3>{p.name}</h3><p>{p.role ? p.role + " · " : ""}{p.company}</p><p>{p.fit_reason}</p><p className="fine">Stage: {p.stage || "new"}{p.contact_email ? " · " + p.contact_email : ""}</p><p><a href={p.evidence_url} target="_blank" rel="noreferrer">Open evidence source</a></p></article>) : <article className="card"><p>No prospects saved yet.</p></article>}</div></section>
        <section className="section"><h2>Draft review queue</h2><p className="fine">Approving a draft does not send it. Sending remains a separate explicit action.</p><div className="cards">{drafts.length ? drafts.map(d=><article className="card" key={d.id}><p className="eyebrow">{d.channel || "Outreach"} · {d.status}</p><h3>{d.subject || d.prospect_name || "Outreach draft"}</h3><p>{d.body || "Draft content is not available."}</p>{d.status === "pending_approval" && <div className="actions"><button type="button" className="button" disabled={busy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={() => reviewDraft(d,"approved")}>Approve draft</button><button type="button" className="button secondary" disabled={busy || !["owner","admin"].includes(workspaces.find(w=>w.id===workspaceId)?.role || "")} onClick={() => reviewDraft(d,"rejected")}>Reject</button></div>}</article>) : <article className="card"><p>No drafts yet. Draft generation requires configured paid entitlements and eligible prospect evidence.</p></article>}</div></section>
      </>}
    </main>
    <footer className="wrap"><p>Private workspace · <Link href="/privacy">Privacy</Link> · <Link href="/terms">Terms</Link> · <Link href="/">Public site</Link></p></footer>
  </>;
}
