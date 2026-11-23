"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { BrandMark } from "../components/site-chrome";

type Plan = { slug: string; name: string; description: string; price_id: string; display_price: string | null; currency: string | null; billing_interval: string | null; entitlements: Record<string, { enabled: boolean; monthly_limit?: number | null }>; active: boolean; created_at?: string; updated_at?: string };
type Client = { workspace_id: string; workspace_name: string; owner_email: string | null; subscription_status: string | null; package_name: string | null; billing_period_starts_at: string | null; billing_period_ends_at: string | null; usage_consumed: number; usage_reserved: number; usage_released: number };
type UsageFeature = { workspace_id: string; feature: string; consumed: number; reserved: number; released: number };
type ClientDetail = { workspace: { workspace_id: string; workspace_name: string; created_at: string | null }; workspace_integrity: { memberships_total: number; active_memberships: number; active_owners: number; verified_active_members: number; active_memberships_for_inactive_accounts: number; active_memberships_for_unverified_accounts: number; pending_accounts: number; issues: string[] }; account_lifecycle_events: { id: number; actor_user_id: string | null; actor_email: string | null; event_type: string; outcome: string; created_at: string | null; metadata: Record<string, string | number | boolean | null> }[]; subscription: { provider?: string; subscription_status?: string | null; plan_slug?: string | null; package_name?: string | null; billing_period_starts_at?: string | null; billing_period_ends_at?: string | null; entitlements?: Record<string, { enabled: boolean; monthly_limit?: number | null }> | null }; members: { user_id: string; email: string; role: string; status: string; account_status: string; account_created_at: string; email_verified_at: string | null; last_login_at: string | null; created_at: string }[]; usage_by_feature: UsageFeature[]; recent_usage: UsageRecord[]; billing_transactions: { provider: string; transaction_id: string; invoice_number: string | null; status: string; currency_code: string | null; total_minor: string | null; billed_at: string; updated_at: string }[]; subscription_events: { provider: string; provider_event_id: string; provider_subscription_id: string; event_created_at: string; received_at: string; outcome: string }[] };
type UsageRecord = { reservation_id: string; workspace_id: string; workspace_name: string | null; feature: string; status: string; created_at: string; updated_at: string; billing_period_starts_at: string; billing_period_ends_at: string };
type AdminEvent = { id: number; actor_email: string; event_type: string; target_type: string; target_id: string; created_at: string };
type Overview = { totals: Record<string, number>; clients: Client[]; plans: Plan[]; usage_by_feature: UsageFeature[]; recent_usage: UsageRecord[]; admin_events: AdminEvent[]; clients_truncated: boolean; clients_offset: number; clients_limit: number; clients_total: number; usage_offset: number; usage_limit: number; usage_total: number; usage_truncated: boolean; audit_offset: number; audit_limit: number; audit_total: number; audit_truncated: boolean; audit_search: string };
type BillingReconciliationItem = { workspace_id: string; workspace_name: string; owner_email: string | null; provider: string; provider_customer_id: string | null; provider_subscription_id: string | null; plan_slug: string | null; subscription_status: string; billing_period_starts_at: string; billing_period_ends_at: string; provider_event_created_at: string | null; subscription_updated_at: string; plan_name: string | null; latest_transaction_id: string | null; latest_invoice_number: string | null; latest_transaction_status: string | null; latest_currency_code: string | null; latest_total_minor: string | null; latest_billed_at: string | null; latest_subscription_event_id: string | null; latest_subscription_event_outcome: string | null; latest_subscription_event_at: string | null; issues: string[] };
type BillingReconciliation = { summary: Record<string, number>; items: BillingReconciliationItem[]; limit: number; offset: number; total: number; truncated: boolean; search: string; read_only: boolean };
type BillingEvent = { event_kind: string; provider: string; provider_event_id: string; workspace_id: string | null; workspace_name: string | null; related_id: string; event_created_at: string; received_at: string; outcome: string; transaction_status: string | null; invoice_number: string | null };
type BillingEvents = { items: BillingEvent[]; limit: number; offset: number; total: number; truncated: boolean; search: string; read_only: boolean; payloads_exposed: boolean };

const emptyPlan = { slug: "", name: "", description: "", price_id: "", display_price: "", currency: "USD", billing_interval: "month", entitlements: '{\n  "ai_draft_generations": { "enabled": true, "monthly_limit": 100 },\n  "email_sends": { "enabled": true, "monthly_limit": 1000 },\n  "website_audits": { "enabled": true, "monthly_limit": 25 },\n  "whatsapp_sends": { "enabled": false, "monthly_limit": 0 },\n  "prospect_research": { "enabled": true, "monthly_limit": 100 }\n}', active: true };

function formatAdminDate(value: string | null | undefined, withTime = false): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return withTime ? date.toLocaleString() : date.toLocaleDateString();
}

async function api<T>(path: string, csrf?: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body) headers.set("Content-Type", "application/json");
  if (csrf && options.method && options.method !== "GET") headers.set("X-CSRF-Token", csrf);
  const response = await fetch(path, { ...options, headers, credentials: "same-origin", cache: "no-store" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Request failed (" + response.status + ")");
  return data as T;
}

export default function PlatformAdminPage() {
  const [csrf, setCsrf] = useState("");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [form, setForm] = useState(emptyPlan);
  const [editing, setEditing] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [platformSmtp, setPlatformSmtp] = useState<{ configuration_complete: boolean; missing_fields: string[]; connection_tested: boolean } | null>(null);
  const [smtpBusy, setSmtpBusy] = useState(false);
  const [clientSearch, setClientSearch] = useState("");
  const [clientQuery, setClientQuery] = useState("");
  const [clientDetail, setClientDetail] = useState<ClientDetail | null>(null);
  const [clientDetailLoading, setClientDetailLoading] = useState(false);
  const [billingReconciliation, setBillingReconciliation] = useState<BillingReconciliation | null>(null);
  const [billingSearch, setBillingSearch] = useState("");
  const [billingQuery, setBillingQuery] = useState("");
  const [billingOffset, setBillingOffset] = useState(0);
  const [billingLoading, setBillingLoading] = useState(false);
  const [billingEvents, setBillingEvents] = useState<BillingEvents | null>(null);
  const [billingEventSearch, setBillingEventSearch] = useState("");
  const [billingEventQuery, setBillingEventQuery] = useState("");
  const [billingEventOffset, setBillingEventOffset] = useState(0);
  const [billingEventsLoading, setBillingEventsLoading] = useState(false);
  const [clientOffset, setClientOffset] = useState(0);
  const [usageOffset, setUsageOffset] = useState(0);
  const [auditOffset, setAuditOffset] = useState(0);
  const [auditSearch, setAuditSearch] = useState("");
  const [auditQuery, setAuditQuery] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState<string | null>(null);
  const filteredClients = overview?.clients ?? [];

  async function loadBillingReconciliation(token: string, offset = 0, search = "") {
    setBillingLoading(true);
    try {
      const result = await api<BillingReconciliation>("/api/v1/platform-admin/billing/reconciliation?limit=50&offset=" + offset + "&search=" + encodeURIComponent(search), token);
      setBillingReconciliation(result);
      setBillingOffset(result.offset);
      setBillingQuery(search);
    } finally { setBillingLoading(false); }
  }

  async function loadBillingEvents(token: string, offset = 0, search = "") {
    setBillingEventsLoading(true);
    try {
      const result = await api<BillingEvents>("/api/v1/platform-admin/billing/events?limit=50&offset=" + offset + "&search=" + encodeURIComponent(search), token);
      setBillingEvents(result);
      setBillingEventOffset(result.offset);
      setBillingEventQuery(search);
    } finally { setBillingEventsLoading(false); }
  }

  async function loadClientDetail(workspaceId: string) {
    if (!csrf || clientDetailLoading) return;
    if (clientDetail?.workspace.workspace_id === workspaceId) { setClientDetail(null); return; }
    setClientDetail(null); setClientDetailLoading(true); setError(""); setNotice("");
    try {
      const detail = await api<ClientDetail>("/api/v1/platform-admin/clients/" + encodeURIComponent(workspaceId), csrf);
      setClientDetail(detail);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load client details.");
    } finally {
      setClientDetailLoading(false);
    }
  }

  const refresh = useCallback(async (token: string, offset = 0, usagePageOffset = 0, auditPageOffset = 0, search = "", auditSearchValue = "") => {
    const data = await api<Overview>("/api/v1/platform-admin/overview?client_limit=100&client_offset=" + offset + "&usage_limit=100&usage_offset=" + usagePageOffset + "&audit_limit=100&audit_offset=" + auditPageOffset + "&audit_search=" + encodeURIComponent(auditSearchValue) + "&client_search=" + encodeURIComponent(search), token);
    setOverview(data);
    setClientDetail(null);
    setClientOffset(data.clients_offset);
    setClientQuery(search);
    setUsageOffset(data.usage_offset);
    setAuditOffset(data.audit_offset);
    setLastRefreshed(new Date().toISOString());
  }, []);

  async function refreshAll() {
    if (!csrf || refreshing || busy) return;
    setRefreshing(true); setBusy(true); setError(""); setNotice("");
    try {
      const [smtp] = await Promise.all([
        api<{ configuration_complete: boolean; missing_fields: string[]; connection_tested: boolean }>("/api/v1/platform-admin/smtp/status", csrf),
        refresh(csrf, clientOffset, usageOffset, auditOffset, clientQuery, auditQuery),
        loadBillingReconciliation(csrf, billingOffset, billingQuery),
        loadBillingEvents(csrf, billingEventOffset, billingEventQuery),
      ]);
      setPlatformSmtp(smtp);
      setNotice("Platform overview and SMTP readiness refreshed.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Platform data could not be refreshed.");
    } finally { setRefreshing(false); setBusy(false); }
  }

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const session = await api<{ csrf_token: string | null }>("/api/v1/auth/me");
        if (!session.csrf_token) throw new Error("Session security token missing; sign in again.");
        if (!active) return;
        setCsrf(session.csrf_token);
        await refresh(session.csrf_token);
        await loadBillingReconciliation(session.csrf_token);
        await loadBillingEvents(session.csrf_token);
        const smtp = await api<{ configuration_complete: boolean; missing_fields: string[]; connection_tested: boolean }>("/api/v1/platform-admin/smtp/status", session.csrf_token);
        if (active) setPlatformSmtp(smtp);
      } catch (e) { if (active) setError(e instanceof Error ? e.message : "Admin access unavailable."); }
    })();
    return () => { active = false; };
  }, [refresh]);

  function startEdit(plan: Plan) {
    setEditing(plan.slug);
    setForm({ slug: plan.slug, name: plan.name, description: plan.description || "", price_id: plan.price_id, display_price: plan.display_price || "", currency: plan.currency || "USD", billing_interval: plan.billing_interval || "month", entitlements: JSON.stringify(plan.entitlements, null, 2), active: plan.active });
    setError(""); setNotice("");
  }


  async function testPlatformSmtp() {
    setSmtpBusy(true); setError(""); setNotice("");
    try {
      await api<{ status: string; email_sent: boolean }>("/api/v1/platform-admin/smtp/test", csrf, { method: "POST", body: "{}" });
      setPlatformSmtp(current => current ? { ...current, connection_tested: true } : current);
      setNotice("Platform SMTP connection authenticated successfully. No email was sent.");
    } catch (e) {
      setPlatformSmtp(current => current ? { ...current, connection_tested: false } : current);
      setError(e instanceof Error ? e.message : "Platform SMTP connection test failed.");
    } finally { setSmtpBusy(false); }
  }

  async function savePlan(event: FormEvent) {
    event.preventDefault();
    const currentPlan = editing ? overview?.plans.find(plan => plan.slug === editing) : undefined;
    const pricingChanged = Boolean(currentPlan && (
      currentPlan.price_id !== form.price_id.trim() ||
      (currentPlan.display_price || "") !== form.display_price.trim() ||
      (currentPlan.currency || "") !== form.currency.trim() ||
      (currentPlan.billing_interval || "") !== form.billing_interval.trim()
    ));
    if (pricingChanged) {
      const confirmed = window.confirm(
        "Paddle & Vercel Update Required\n\nYou changed this package's pricing. Before considering the change complete:\n\n1. In Paddle, create a new recurring Price under the SAME Product (do not create another package or product).\n2. Update this package's price_id in the Paddle pricing JSON stored in Vercel Environment Variables.\n3. Redeploy the application on Vercel and verify checkout.\n\nExisting subscribers keep their current subscription price unless separately migrated. Continue saving this package now?"
      );
      if (!confirmed) return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      let entitlements: Plan["entitlements"];
      try { entitlements = JSON.parse(form.entitlements); } catch { throw new Error("Entitlements must be valid JSON."); }
      const payload = { slug: form.slug.trim(), name: form.name.trim(), description: form.description, price_id: form.price_id.trim(), display_price: form.display_price || null, currency: form.currency || null, billing_interval: form.billing_interval || null, entitlements, active: form.active };
      await api("/api/v1/platform-admin/plans" + (editing ? "/" + encodeURIComponent(editing) : ""), csrf, { method: editing ? "PATCH" : "POST", body: JSON.stringify(payload) });
      setForm(emptyPlan); setEditing(""); await refresh(csrf, 0, 0, 0, clientQuery);
      setNotice(pricingChanged
        ? "Package saved. Paddle and Vercel synchronization is still required: create a new recurring Price under the same Paddle Product, update this package's price_id in the Vercel pricing JSON, redeploy, and verify checkout."
        : (editing ? "Package updated." : "Package created."));
    } catch (e) { setError(e instanceof Error ? e.message : "Package could not be saved."); }
    finally { setBusy(false); }
  }

  async function importConfiguredPlans() {
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<{ imported: number; skipped: number; configured: number }>("/api/v1/platform-admin/plans/import-configured", csrf, { method: "POST", body: "{}" });
      await refresh(csrf, 0, 0, 0, clientQuery);
      setNotice("Imported " + result.imported + " package(s); skipped " + result.skipped + " existing or invalid entry/entries from " + result.configured + " configured plan(s). Existing database packages were not overwritten.");
    } catch (e) { setError(e instanceof Error ? e.message : "Configured packages could not be imported."); }
    finally { setBusy(false); }
  }

  async function deactivate(plan: Plan) {
    if (!window.confirm("Deactivate package '" + plan.name + "'? Existing subscription history remains intact.")) return;
    setBusy(true); setError(""); setNotice("");
    try { await api("/api/v1/platform-admin/plans/" + encodeURIComponent(plan.slug), csrf, { method: "DELETE" }); await refresh(csrf, 0, 0, 0, clientQuery); setNotice("Package deactivated. Historic records were preserved."); }
    catch (e) { setError(e instanceof Error ? e.message : "Package could not be deactivated."); }
    finally { setBusy(false); }
  }

  return <main className="page-shell platform-admin-shell">
    <header className="page-header platform-admin-header"><Link className="brand" href="/" aria-label="Outreach Marketing Agent home"><BrandMark/><span className="brand-name">Outreach<small>Marketing Agent</small></span></Link><p className="eyebrow">Platform operations</p><h1>SaaS administration</h1><p>Global client, subscription, package and usage visibility. Access is restricted by the server-side platform-admin email allowlist.</p><div className="platform-admin-header-actions"><Link href="/dashboard">Return to workspace dashboard</Link><button className="button secondary" type="button" disabled={!csrf || refreshing || busy} onClick={refreshAll}>{refreshing ? "Refreshing…" : "Refresh platform data"}</button>{lastRefreshed && <span className="fine">Last refreshed {new Date(lastRefreshed).toLocaleTimeString()}</span>}</div></header>
    {error && <p className="notice" role="alert">{error}</p>}{notice && <p className="notice" role="status">{notice}</p>}
    {!overview && !error && <section className="card"><p>Loading protected platform summary…</p></section>}
    {overview && <>

      <section className="section" aria-labelledby="platform-smtp-title">
        <h2 id="platform-smtp-title">Platform SMTP (system emails)</h2>
        <p className="fine">Used only for platform account verification, password resets and operational emails. Customer outreach continues to use each workspace's own SMTP account.</p>
        <div className="card">
          <p>{platformSmtp ? (platformSmtp.configuration_complete ? "Configuration complete" : "Configuration incomplete") : "Checking platform SMTP configuration…"}</p>
          {platformSmtp && !platformSmtp.configuration_complete && <p className="fine">Missing or invalid settings: {platformSmtp.missing_fields.join(", ")}</p>}
          <p className="fine">Connection test: {platformSmtp?.connection_tested ? "Passed" : "Not tested in this session"}</p>
          <button className="button secondary" type="button" disabled={smtpBusy || !csrf || !platformSmtp?.configuration_complete} onClick={testPlatformSmtp}>{smtpBusy ? "Testing…" : "Test Platform SMTP (no email sent)"}</button>
        </div>
      </section>
      <section className="section" aria-labelledby="totals-title"><h2 id="totals-title">Platform totals</h2><div className="metric-grid">
        {Object.entries(overview.totals).map(([key,value]) => <article className="card" key={key}><p className="fine">{key.replaceAll("_"," ")}</p><p className="metric-value">{value.toLocaleString()}</p></article>)}
      </div></section>
      <section className="section" aria-labelledby="billing-reconciliation-title">
        <h2 id="billing-reconciliation-title">Billing reconciliation</h2>
        <p className="fine">Read-only comparison of verified subscription snapshots, provider event history and sanitized invoice transactions. Flags are review indicators, not automatic billing decisions. No provider calls, payment changes or customer notifications are performed.</p>
        {billingReconciliation && <div className="metric-grid">
          <article className="card"><p className="fine">Subscriptions checked</p><p className="metric-value">{billingReconciliation.summary.subscriptions_total.toLocaleString()}</p></article>
          <article className="card"><p className="fine">Needs review</p><p className="metric-value">{billingReconciliation.summary.needs_review.toLocaleString()}</p></article>
          <article className="card"><p className="fine">Payment attention</p><p className="metric-value">{billingReconciliation.summary.payment_attention.toLocaleString()}</p></article>
          <article className="card"><p className="fine">Plan not mapped</p><p className="metric-value">{billingReconciliation.summary.plan_not_mapped.toLocaleString()}</p></article>
          <article className="card"><p className="fine">Missing invoice history</p><p className="metric-value">{billingReconciliation.summary.missing_transaction_history.toLocaleString()}</p></article>
          <article className="card"><p className="fine">Missing subscription events</p><p className="metric-value">{billingReconciliation.summary.missing_subscription_event_history.toLocaleString()}</p></article>
          <article className="card"><p className="fine">Expired active periods</p><p className="metric-value">{billingReconciliation.summary.expired_active_periods.toLocaleString()}</p></article>
          <article className="card"><p className="fine">Payment-state conflicts</p><p className="metric-value">{billingReconciliation.summary.payment_status_conflicts.toLocaleString()}</p></article>
        </div>}
        <form className="field" onSubmit={async event => { event.preventDefault(); try { await loadBillingReconciliation(csrf, 0, billingSearch.trim()); } catch (e) { setError(e instanceof Error ? e.message : "Billing reconciliation could not be loaded."); } }}>
          <label htmlFor="billing-reconciliation-search">Search subscriptions and invoice records</label>
          <div className="actions"><input id="billing-reconciliation-search" type="search" maxLength={200} value={billingSearch} onChange={e=>setBillingSearch(e.target.value)} placeholder="Workspace, owner, provider, plan, subscription or invoice ID"/><button className="button secondary" type="submit" disabled={billingLoading || !csrf}>Search</button><button className="button secondary" type="button" disabled={billingLoading || !billingQuery} onClick={async()=>{setBillingSearch("");try{await loadBillingReconciliation(csrf,0,"");}catch(e){setError(e instanceof Error?e.message:"Billing reconciliation could not be loaded.");}}}>Clear</button></div>
          <p className="fine" aria-live="polite">{billingReconciliation ? "Showing " + billingReconciliation.items.length + " of " + billingReconciliation.total.toLocaleString() + " subscriptions" + (billingQuery ? " matching “" + billingQuery + "”" : "") + "." : "Loading reconciliation data…"}</p>
        </form>
        <div className="card table-wrap"><table><thead><tr><th>Workspace / owner</th><th>Subscription</th><th>Latest invoice transaction</th><th>Provider event</th><th>Review flags</th></tr></thead><tbody>
          {billingReconciliation?.items.map(item=><tr key={item.workspace_id}>
            <td><strong>{item.workspace_name}</strong><br/><span className="fine">{item.owner_email || "Owner not mapped"}</span><br/><span className="fine">{item.workspace_id}</span></td>
            <td>{item.plan_name || item.plan_slug || "Plan unmapped"}<br/><span className="fine">{item.provider} · {item.subscription_status}</span><br/><span className="fine">{item.provider_subscription_id || "Provider subscription ID missing"}</span><br/><span className="fine">{item.billing_period_starts_at ? new Date(item.billing_period_starts_at).toLocaleDateString() : "—"} – {item.billing_period_ends_at ? new Date(item.billing_period_ends_at).toLocaleDateString() : "—"}</span></td>
            <td>{item.latest_transaction_id || "No transaction"}<br/><span className="fine">{item.latest_invoice_number || "Invoice number unavailable"} · {item.latest_transaction_status || "—"}</span><br/><span className="fine">{item.latest_billed_at ? new Date(item.latest_billed_at).toLocaleDateString() : "—"}{item.latest_total_minor !== null ? " · " + item.latest_total_minor + " " + (item.latest_currency_code || "") + " minor units" : ""}</span></td>
            <td>{item.latest_subscription_event_id || "No event"}<br/><span className="fine">{item.latest_subscription_event_outcome || "—"}</span><br/><span className="fine">{item.latest_subscription_event_at ? new Date(item.latest_subscription_event_at).toLocaleString() : "—"}</span></td>
            <td>{item.issues.length ? <ul className="billing-issue-list">{item.issues.map(issue=><li key={issue}>{issue.replaceAll("_"," ")}</li>)}</ul> : <span>Looks consistent</span>}</td>
          </tr>)}
        </tbody></table>{billingReconciliation && !billingReconciliation.items.length && <p>No subscription records match this search.</p>}</div>
        <div className="section" aria-labelledby="billing-event-history-title">
          <h3 id="billing-event-history-title">Verified billing event timeline</h3>
          <p className="fine">Chronological, read-only history of subscription and transaction webhook events. Only normalized identifiers and statuses are shown; raw webhook payloads, signatures and secrets are never exposed.</p>
          <form className="field" onSubmit={async event => { event.preventDefault(); try { await loadBillingEvents(csrf, 0, billingEventSearch.trim()); } catch (e) { setError(e instanceof Error ? e.message : "Billing event history could not be loaded."); } }}>
            <label htmlFor="billing-event-search">Search event history</label>
            <div className="actions"><input id="billing-event-search" type="search" maxLength={200} value={billingEventSearch} onChange={e=>setBillingEventSearch(e.target.value)} placeholder="Event ID, workspace, provider, invoice or status"/><button className="button secondary" type="submit" disabled={billingEventsLoading || !csrf}>Search events</button><button className="button secondary" type="button" disabled={billingEventsLoading || !billingEventQuery} onClick={async()=>{setBillingEventSearch("");try{await loadBillingEvents(csrf,0,"");}catch(e){setError(e instanceof Error?e.message:"Billing event history could not be loaded.");}}}>Clear</button></div>
            <p className="fine" aria-live="polite">{billingEvents ? "Showing " + billingEvents.items.length + " of " + billingEvents.total.toLocaleString() + " verified events" + (billingEventQuery ? " matching “" + billingEventQuery + "”" : "") + "." : "Loading event history…"}</p>
          </form>
          <div className="card table-wrap"><table><thead><tr><th>Event received</th><th>Workspace</th><th>Event type</th><th>Provider event ID</th><th>Outcome / transaction</th></tr></thead><tbody>
            {billingEvents?.items.map((event,index)=><tr key={event.provider + ":" + event.provider_event_id + ":" + event.event_kind + ":" + index}>
              <td>{new Date(event.event_created_at).toLocaleString()}<br/><span className="fine">Received {new Date(event.received_at).toLocaleString()}</span></td>
              <td>{event.workspace_name || "Workspace not mapped"}<br/><span className="fine">{event.workspace_id || "Workspace ID unavailable"}</span></td>
              <td>{event.event_kind} · {event.provider}</td>
              <td>{event.provider_event_id}</td>
              <td>{event.outcome}{event.transaction_status ? " · " + event.transaction_status : ""}<br/><span className="fine">{event.invoice_number || event.related_id}</span></td>
            </tr>)}
          </tbody></table>{billingEvents && !billingEvents.items.length && <p>No verified billing events match this search.</p>}</div>
          <div className="actions" aria-label="Billing event history pagination">
            <button className="button secondary" type="button" disabled={billingEventsLoading || billingEventOffset===0} onClick={async()=>{try{await loadBillingEvents(csrf,Math.max(0,billingEventOffset-50),billingEventQuery);}catch(e){setError(e instanceof Error?e.message:"Could not load previous billing events.");}}}>Previous events</button>
            <span className="fine">Events {billingEvents?.total ? billingEventOffset+1 : 0}–{Math.min(billingEventOffset+(billingEvents?.items.length||0),billingEvents?.total||0)} of {billingEvents?.total||0}</span>
            <button className="button secondary" type="button" disabled={billingEventsLoading || !billingEvents?.truncated} onClick={async()=>{try{await loadBillingEvents(csrf,billingEventOffset+50,billingEventQuery);}catch(e){setError(e instanceof Error?e.message:"Could not load next billing events.");}}}>Next events</button>
          </div>
        </div>
        <div className="actions" aria-label="Billing reconciliation pagination">
          <button className="button secondary" type="button" disabled={billingLoading || billingOffset===0} onClick={async()=>{try{await loadBillingReconciliation(csrf,Math.max(0,billingOffset-50),billingQuery);}catch(e){setError(e instanceof Error?e.message:"Could not load previous billing records.");}}}>Previous</button>
          <span className="fine">Subscriptions {billingReconciliation?.total ? billingOffset+1 : 0}–{Math.min(billingOffset+(billingReconciliation?.items.length||0),billingReconciliation?.total||0)} of {billingReconciliation?.total||0}</span>
          <button className="button secondary" type="button" disabled={billingLoading || !billingReconciliation?.truncated} onClick={async()=>{try{await loadBillingReconciliation(csrf,billingOffset+50,billingQuery);}catch(e){setError(e instanceof Error?e.message:"Could not load next billing records.");}}}>Next</button>
        </div>
      </section>
      <section className="section" aria-labelledby="plans-title"><h2 id="plans-title">Package management</h2><p className="fine">Price IDs are shown only to authorized platform admins. Deleting a package is a soft-deactivation so billing history is retained.</p><div className="actions"><button className="button secondary" type="button" disabled={busy || !csrf} onClick={importConfiguredPlans}>Import configured Paddle packages</button><span className="fine">Imports environment-configured packages only when the slug and price ID are not already present. Existing admin edits are preserved.</span></div>
        <form className="card form-grid" onSubmit={savePlan}>
          <h3>{editing ? "Edit package: " + editing : "Add package"}</h3>
          <div className="field"><label htmlFor="slug">Package slug</label><input id="slug" required maxLength={80} pattern="[a-z0-9][a-z0-9_-]*" disabled={!!editing} value={form.slug} onChange={e=>setForm({...form,slug:e.target.value})}/></div>
          <div className="field"><label htmlFor="plan-name">Display name</label><input id="plan-name" required maxLength={120} value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></div>
          <div className="field"><label htmlFor="price-id">Paddle price ID</label><input id="price-id" required maxLength={120} pattern="pri_[A-Za-z0-9_-]+" value={form.price_id} onChange={e=>setForm({...form,price_id:e.target.value})}/></div>
          <div className="field"><label htmlFor="display-price">Display price</label><input id="display-price" maxLength={80} value={form.display_price} onChange={e=>setForm({...form,display_price:e.target.value})} placeholder="e.g. 29.00"/></div>
          <div className="field"><label htmlFor="currency">Currency</label><input id="currency" maxLength={8} value={form.currency} onChange={e=>setForm({...form,currency:e.target.value})}/></div>
          <div className="field"><label htmlFor="interval">Billing interval</label><input id="interval" maxLength={40} value={form.billing_interval} onChange={e=>setForm({...form,billing_interval:e.target.value})}/></div>
          <div className="field"><label htmlFor="description">Description</label><textarea id="description" maxLength={500} value={form.description} onChange={e=>setForm({...form,description:e.target.value})}/></div>
          <div className="field"><label htmlFor="entitlements">Entitlements / limits (JSON)</label><textarea id="entitlements" required rows={8} value={form.entitlements} onChange={e=>setForm({...form,entitlements:e.target.value})}/><p className="fine">Example: {"{ \"prospect_search\": { \"enabled\": true, \"monthly_limit\": 100 } }"}</p></div>
          <label className="checkbox-field"><input type="checkbox" checked={form.active} onChange={e=>setForm({...form,active:e.target.checked})}/> Package active for new checkout</label>
          <div className="actions"><button className="button" disabled={busy || !csrf}>{busy ? "Saving…" : editing ? "Save changes" : "Create package"}</button>{editing && <button className="button secondary" type="button" disabled={busy} onClick={()=>{setEditing("");setForm(emptyPlan);}}>Cancel edit</button>}</div>
        </form>
        <div className="card table-wrap"><table><thead><tr><th>Package</th><th>Price</th><th>Status</th><th>Limits / features</th><th>Actions</th></tr></thead><tbody>{overview.plans.map(plan=><tr key={plan.slug}><td><strong>{plan.name}</strong><br/><span className="fine">{plan.slug}</span></td><td>{plan.display_price || "Not set"} {plan.currency || ""}<br/><span className="fine">{plan.billing_interval || "interval not set"}</span></td><td>{plan.active ? "Active" : "Inactive"}</td><td>{Object.entries(plan.entitlements || {}).map(([feature,rule])=><div key={feature}>{feature}: {rule.enabled ? "on" : "off"} · {rule.monthly_limit == null ? "unlimited" : rule.monthly_limit + "/period"}</div>)}</td><td><div className="actions"><button className="button secondary" type="button" disabled={busy} onClick={()=>startEdit(plan)}>Edit</button>{plan.active && <button className="button secondary" type="button" disabled={busy} onClick={()=>deactivate(plan)}>Deactivate</button>}</div></td></tr>)}</tbody></table>{!overview.plans.length && <p>No database-managed packages yet. Create the first package to activate database catalog management.</p>}</div>
      </section>
      <section className="section" aria-labelledby="clients-title"><h2 id="clients-title">Clients and usage</h2><p className="fine">Usage figures are persisted reservation counts, not inferred revenue. Client search is applied server-side across all workspaces before pagination.</p>
        <form className="field" onSubmit={async event => { event.preventDefault(); setBusy(true); setError(""); try { await refresh(csrf, 0, usageOffset, auditOffset, clientSearch.trim()); } catch (e) { setError(e instanceof Error ? e.message : "Could not search all clients."); } finally { setBusy(false); } }}><label htmlFor="client-search">Search all clients</label><div className="actions"><input id="client-search" type="search" maxLength={200} value={clientSearch} onChange={e => setClientSearch(e.target.value)} placeholder="Workspace, owner email, package, ID or subscription status"/><button className="button secondary" type="submit" disabled={busy || !csrf}>Search</button><button className="button secondary" type="button" disabled={busy || !clientQuery} onClick={async () => { setClientSearch(""); setBusy(true); setError(""); try { await refresh(csrf, 0, usageOffset, auditOffset, ""); } catch (e) { setError(e instanceof Error ? e.message : "Could not clear client search."); } finally { setBusy(false); } }}>Clear</button></div><p className="fine" aria-live="polite">Showing {filteredClients.length} of {overview.clients_total.toLocaleString()} matching workspaces across all client pages{clientQuery ? " for “" + clientQuery + "”" : ""}.</p></form>
        <div className="card table-wrap"><table><thead><tr><th>Workspace</th><th>Owner email</th><th>Package / subscription</th><th>Billing period</th><th>Usage counts</th><th>Details</th></tr></thead><tbody>{filteredClients.map(client=><tr key={client.workspace_id}><td>{client.workspace_name}<br/><span className="fine">{client.workspace_id}</span></td><td>{client.owner_email || "Owner not mapped"}</td><td>{client.package_name || "Package not matched"}<br/><span className="fine">{client.subscription_status || "No subscription"}</span></td><td>{client.billing_period_starts_at ? new Date(client.billing_period_starts_at).toLocaleDateString() : "—"} – {client.billing_period_ends_at ? new Date(client.billing_period_ends_at).toLocaleDateString() : "—"}</td><td>Consumed: {client.usage_consumed}<br/>Reserved: {client.usage_reserved}<br/>Released: {client.usage_released}</td><td><button className="button secondary" type="button" disabled={clientDetailLoading} onClick={() => void loadClientDetail(client.workspace_id)}>{clientDetailLoading ? "Loading details…" : clientDetail?.workspace.workspace_id === client.workspace_id ? "Hide details" : "View details"}</button></td></tr>)}</tbody></table>{!filteredClients.length && <p>{overview.clients.length ? "No clients match this search." : "No workspaces were found."}</p>}</div>
        {clientDetail && <section className="card client-detail-panel"><div className="client-detail-heading"><div><h3 id="client-detail-title">{clientDetail.workspace.workspace_name} — customer details</h3><p className="fine">Read-only account, subscription and quota view · Workspace {clientDetail.workspace.workspace_id}</p></div><button className="button secondary" type="button" onClick={() => setClientDetail(null)}>Close</button></div><div className="metric-grid client-detail-metrics"><article className="card client-detail-stat"><span>Subscription</span><strong>{clientDetail.subscription.subscription_status || "None"}</strong></article><article className="stat-card"><span>Package</span><strong>{clientDetail.subscription.package_name || clientDetail.subscription.plan_slug || "Unassigned"}</strong></article><article className="stat-card"><span>Members</span><strong>{clientDetail.members.length}</strong></article><article className="stat-card"><span>Provider</span><strong>{clientDetail.subscription.provider || "—"}</strong></article><article className="stat-card"><span>Billing period</span><strong>{formatAdminDate(clientDetail.subscription.billing_period_starts_at)} – {formatAdminDate(clientDetail.subscription.billing_period_ends_at)}</strong></article></div><h4>Workspace integrity</h4><div className="metric-grid client-detail-metrics"><article className="stat-card"><span>Active memberships</span><strong>{clientDetail.workspace_integrity.active_memberships}</strong></article><article className="stat-card"><span>Active owners</span><strong>{clientDetail.workspace_integrity.active_owners}</strong></article><article className="stat-card"><span>Verified active members</span><strong>{clientDetail.workspace_integrity.verified_active_members}</strong></article><article className="stat-card"><span>Pending accounts</span><strong>{clientDetail.workspace_integrity.pending_accounts}</strong></article></div>{clientDetail.workspace_integrity.issues.length ? <ul className="client-integrity-issues">{clientDetail.workspace_integrity.issues.map(issue=><li key={issue}>{issue.replaceAll("_"," ")}</li>)}</ul> : <p className="fine">No membership/account consistency flags detected by these checks.</p>}<h4>Workspace members and account lifecycle</h4><div className="table-wrap"><table><thead><tr><th>Email</th><th>Account created</th><th>Role</th><th>Membership</th><th>Account</th><th>Email verified</th><th>Last login</th></tr></thead><tbody>{clientDetail.members.map(member=><tr key={member.user_id}><td>{member.email}</td><td>{formatAdminDate(member.account_created_at)}</td><td>{member.role}</td><td>{member.status}</td><td>{member.account_status}</td><td>{member.email_verified_at ? formatAdminDate(member.email_verified_at) : "No"}</td><td>{formatAdminDate(member.last_login_at,true) === "—" ? "Never" : formatAdminDate(member.last_login_at,true)}</td></tr>)}</tbody></table>{!clientDetail.members.length && <p>No workspace members found.</p>}</div><h4>Recent account and workspace events</h4><div className="table-wrap"><table><thead><tr><th>Time</th><th>Event</th><th>Actor</th><th>Outcome</th><th>Safe details</th></tr></thead><tbody>{clientDetail.account_lifecycle_events.map(event=><tr key={event.id}><td>{formatAdminDate(event.created_at,true)}</td><td>{event.event_type}</td><td>{event.actor_email || event.actor_user_id || "System"}</td><td>{event.outcome}</td><td>{Object.entries(event.metadata).map(([key,value])=>key.replaceAll("_"," ")+": "+String(value ?? "—")).join(" · ") || "—"}</td></tr>)}</tbody></table>{!clientDetail.account_lifecycle_events.length && <p>No account/workspace audit events found.</p>}</div><h4>Feature usage</h4><div className="table-wrap"><table><thead><tr><th>Feature</th><th>Consumed</th><th>Reserved</th><th>Released</th></tr></thead><tbody>{clientDetail.usage_by_feature.map(item=><tr key={item.feature}><td>{item.feature}</td><td>{item.consumed}</td><td>{item.reserved}</td><td>{item.released}</td></tr>)}</tbody></table>{!clientDetail.usage_by_feature.length && <p>No feature usage recorded.</p>}</div><h4>Subscription entitlements</h4><pre className="client-entitlements">{JSON.stringify(clientDetail.subscription.entitlements || {}, null, 2)}</pre><h4>Recent invoices and transactions</h4><div className="table-wrap"><table><thead><tr><th>Billed</th><th>Provider / transaction</th><th>Invoice</th><th>Status</th><th>Amount</th></tr></thead><tbody>{clientDetail.billing_transactions.map(item=><tr key={item.provider + ":" + item.transaction_id}><td>{formatAdminDate(item.billed_at,true)}</td><td>{item.provider}<br/><span className="fine">{item.transaction_id}</span></td><td>{item.invoice_number || "—"}</td><td>{item.status}</td><td>{item.total_minor !== null ? item.total_minor + " " + (item.currency_code || "") + " minor units" : "—"}</td></tr>)}</tbody></table>{!clientDetail.billing_transactions.length && <p>No invoice transactions found.</p>}</div><h4>Subscription lifecycle events</h4><div className="table-wrap"><table><thead><tr><th>Event time</th><th>Provider</th><th>Event ID</th><th>Subscription</th><th>Outcome</th></tr></thead><tbody>{clientDetail.subscription_events.map(item=><tr key={item.provider + ":" + item.provider_event_id}><td>{formatAdminDate(item.event_created_at,true)}<br/><span className="fine">Received {formatAdminDate(item.received_at,true)}</span></td><td>{item.provider}</td><td>{item.provider_event_id}</td><td>{item.provider_subscription_id}</td><td>{item.outcome}</td></tr>)}</tbody></table>{!clientDetail.subscription_events.length && <p>No subscription lifecycle events found.</p>}</div><h4>Recent quota reservations</h4><div className="table-wrap"><table><thead><tr><th>Created</th><th>Feature</th><th>Status</th><th>Billing period</th></tr></thead><tbody>{clientDetail.recent_usage.map(item=><tr key={item.reservation_id}><td>{new Date(item.created_at).toLocaleString()}</td><td>{item.feature}</td><td>{item.status}</td><td>{formatAdminDate(item.billing_period_starts_at)} – {formatAdminDate(item.billing_period_ends_at)}</td></tr>)}</tbody></table>{!clientDetail.recent_usage.length && <p>No quota reservations found.</p>}</div></section>}
        <div className="actions" aria-label="Client pagination">
          <button className="button secondary" type="button" disabled={busy || clientOffset === 0} onClick={async () => { setBusy(true); setError(""); try { await refresh(csrf, Math.max(0, clientOffset - overview.clients_limit), usageOffset, auditOffset, clientQuery); } catch (e) { setError(e instanceof Error ? e.message : "Could not load previous clients."); } finally { setBusy(false); } }}>Previous page</button>
          <span className="fine">Workspaces {overview.clients_total === 0 ? 0 : clientOffset + 1}–{Math.min(clientOffset + overview.clients.length, overview.clients_total)} of {overview.clients_total}</span>
          <button className="button secondary" type="button" disabled={busy || !overview.clients_truncated} onClick={async () => { setBusy(true); setError(""); try { await refresh(csrf, clientOffset + overview.clients_limit, usageOffset, auditOffset, clientQuery); } catch (e) { setError(e instanceof Error ? e.message : "Could not load next clients."); } finally { setBusy(false); } }}>Next page</button>
        </div>
      </section>
      <section className="section" aria-labelledby="feature-usage-title"><h2 id="feature-usage-title">Usage by client and feature</h2>
        <div className="card table-wrap"><table><thead><tr><th>Workspace ID</th><th>Feature</th><th>Consumed</th><th>Reserved</th><th>Released</th></tr></thead><tbody>{overview.usage_by_feature.map((item,index)=><tr key={item.workspace_id + ":" + item.feature + ":" + index}><td>{item.workspace_id}</td><td>{item.feature}</td><td>{item.consumed}</td><td>{item.reserved}</td><td>{item.released}</td></tr>)}</tbody></table>{!overview.usage_by_feature.length && <p>No feature usage records yet.</p>}</div>
      </section>
      <section className="section" aria-labelledby="usage-history-title"><h2 id="usage-history-title">Recent usage history</h2><p className="fine">Paginated persisted reservation history; no prompts, credentials, or message bodies are exposed.</p>
        <div className="card table-wrap"><table><thead><tr><th>Created</th><th>Client</th><th>Feature</th><th>Status</th><th>Billing period</th><th>Reservation ID</th></tr></thead><tbody>{overview.recent_usage.map(item=><tr key={item.reservation_id}><td>{new Date(item.created_at).toLocaleString()}</td><td>{item.workspace_name || item.workspace_id}</td><td>{item.feature}</td><td>{item.status}</td><td>{item.billing_period_starts_at ? new Date(item.billing_period_starts_at).toLocaleDateString() : "—"} – {item.billing_period_ends_at ? new Date(item.billing_period_ends_at).toLocaleDateString() : "—"}</td><td>{item.reservation_id}</td></tr>)}</tbody></table>{!overview.recent_usage.length && <p>No usage history yet.</p>}</div>
        <div className="actions" aria-label="Usage history pagination">
          <button className="button secondary" type="button" disabled={busy || usageOffset === 0} onClick={async () => { setBusy(true); setError(""); try { await refresh(csrf, clientOffset, Math.max(0, usageOffset - overview.usage_limit), auditOffset, clientQuery); } catch (e) { setError(e instanceof Error ? e.message : "Could not load previous usage records."); } finally { setBusy(false); } }}>Previous usage</button>
          <span className="fine">Records {overview.usage_total === 0 ? 0 : usageOffset + 1}–{Math.min(usageOffset + overview.recent_usage.length, overview.usage_total)} of {overview.usage_total.toLocaleString()}</span>
          <button className="button secondary" type="button" disabled={busy || !overview.usage_truncated} onClick={async () => { setBusy(true); setError(""); try { await refresh(csrf, clientOffset, usageOffset + overview.usage_limit, auditOffset, clientQuery); } catch (e) { setError(e instanceof Error ? e.message : "Could not load next usage records."); } finally { setBusy(false); } }}>Next usage</button>
        </div>
      </section>
      <section className="section" aria-labelledby="admin-audit-title"><h2 id="admin-audit-title">Platform admin audit history</h2><p className="fine">Search across actor email, action, target and recorded metadata. Results are filtered on the server before pagination.</p><form className="field" onSubmit={async event => { event.preventDefault(); setBusy(true); setError(""); try { setAuditQuery(auditSearch.trim()); await refresh(csrf, clientOffset, usageOffset, 0, clientQuery, auditSearch.trim()); setAuditSearch(auditSearch.trim()); } catch (e) { setError(e instanceof Error ? e.message : "Could not search audit history."); } finally { setBusy(false); } }}><label htmlFor="admin-audit-search">Search audit events</label><div className="actions"><input id="admin-audit-search" type="search" maxLength={200} value={auditSearch} onChange={e=>setAuditSearch(e.target.value)} placeholder="Actor email, action, target ID or metadata"/><button className="button secondary" type="submit" disabled={busy || !csrf}>Search audit</button><button className="button secondary" type="button" disabled={busy || !auditQuery} onClick={async()=>{setAuditSearch("");setBusy(true);setError("");try{setAuditQuery("");await refresh(csrf,clientOffset,usageOffset,0,clientQuery,"");}catch(e){setError(e instanceof Error?e.message:"Could not clear audit search.");}finally{setBusy(false);}}}>Clear</button></div></form>
        <div className="card table-wrap"><table><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Target</th></tr></thead><tbody>{overview.admin_events.map(event=><tr key={event.id}><td>{new Date(event.created_at).toLocaleString()}</td><td>{event.actor_email}</td><td>{event.event_type}</td><td>{event.target_type}: {event.target_id}</td></tr>)}</tbody></table>{!overview.admin_events.length && <p>No platform admin changes recorded yet.</p>}</div>
        <div className="actions" aria-label="Platform audit pagination">
          <button className="button secondary" type="button" disabled={busy || auditOffset === 0} onClick={async () => { setBusy(true); setError(""); try { await refresh(csrf, clientOffset, usageOffset, Math.max(0, auditOffset - overview.audit_limit), clientQuery, auditQuery); } catch (e) { setError(e instanceof Error ? e.message : "Could not load previous audit events."); } finally { setBusy(false); } }}>Previous audit</button>
          <span className="fine">Events {overview.audit_total === 0 ? 0 : auditOffset + 1}–{Math.min(auditOffset + overview.admin_events.length, overview.audit_total)} of {overview.audit_total.toLocaleString()}</span>
          <button className="button secondary" type="button" disabled={busy || !overview.audit_truncated} onClick={async () => { setBusy(true); setError(""); try { await refresh(csrf, clientOffset, usageOffset, auditOffset + overview.audit_limit, clientQuery, auditQuery); } catch (e) { setError(e instanceof Error ? e.message : "Could not load next audit events."); } finally { setBusy(false); } }}>Next audit</button>
        </div>
      </section>
    </>}
  </main>;
}
