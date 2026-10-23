"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";

type Plan = { slug: string; name: string; description: string; price_id: string; display_price: string | null; currency: string | null; billing_interval: string | null; entitlements: Record<string, { enabled: boolean; monthly_limit?: number | null }>; active: boolean; created_at?: string; updated_at?: string };
type Client = { workspace_id: string; workspace_name: string; owner_email: string | null; subscription_status: string | null; billing_period_starts_at: string | null; billing_period_ends_at: string | null; usage_consumed: number; usage_reserved: number; usage_released: number };
type UsageFeature = { workspace_id: string; feature: string; consumed: number; reserved: number; released: number };
type UsageRecord = { reservation_id: string; workspace_id: string; workspace_name: string | null; feature: string; status: string; created_at: string; updated_at: string; billing_period_starts_at: string; billing_period_ends_at: string };
type Overview = { totals: Record<string, number>; clients: Client[]; plans: Plan[]; usage_by_feature: UsageFeature[]; recent_usage: UsageRecord[]; clients_truncated: boolean };

const emptyPlan = { slug: "", name: "", description: "", price_id: "", display_price: "", currency: "USD", billing_interval: "month", entitlements: '{\n  "prospect_search": { "enabled": true, "monthly_limit": 100 }\n}', active: true };

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

  const refresh = useCallback(async (token: string) => {
    const data = await api<Overview>("/api/v1/platform-admin/overview", token);
    setOverview(data);
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const session = await api<{ csrf_token: string | null }>("/api/v1/auth/me");
        if (!session.csrf_token) throw new Error("Session security token missing; sign in again.");
        if (!active) return;
        setCsrf(session.csrf_token);
        await refresh(session.csrf_token);
      } catch (e) { if (active) setError(e instanceof Error ? e.message : "Admin access unavailable."); }
    })();
    return () => { active = false; };
  }, [refresh]);

  function startEdit(plan: Plan) {
    setEditing(plan.slug);
    setForm({ slug: plan.slug, name: plan.name, description: plan.description || "", price_id: plan.price_id, display_price: plan.display_price || "", currency: plan.currency || "USD", billing_interval: plan.billing_interval || "month", entitlements: JSON.stringify(plan.entitlements, null, 2), active: plan.active });
    setError(""); setNotice("");
  }

  async function savePlan(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      let entitlements: Plan["entitlements"];
      try { entitlements = JSON.parse(form.entitlements); } catch { throw new Error("Entitlements must be valid JSON."); }
      const payload = { slug: form.slug.trim(), name: form.name.trim(), description: form.description, price_id: form.price_id.trim(), display_price: form.display_price || null, currency: form.currency || null, billing_interval: form.billing_interval || null, entitlements, active: form.active };
      await api("/api/v1/platform-admin/plans" + (editing ? "/" + encodeURIComponent(editing) : ""), csrf, { method: editing ? "PATCH" : "POST", body: JSON.stringify(payload) });
      setForm(emptyPlan); setEditing(""); await refresh(csrf); setNotice(editing ? "Package updated." : "Package created.");
    } catch (e) { setError(e instanceof Error ? e.message : "Package could not be saved."); }
    finally { setBusy(false); }
  }

  async function deactivate(plan: Plan) {
    if (!window.confirm("Deactivate package '" + plan.name + "'? Existing subscription history remains intact.")) return;
    setBusy(true); setError(""); setNotice("");
    try { await api("/api/v1/platform-admin/plans/" + encodeURIComponent(plan.slug), csrf, { method: "DELETE" }); await refresh(csrf); setNotice("Package deactivated. Historic records were preserved."); }
    catch (e) { setError(e instanceof Error ? e.message : "Package could not be deactivated."); }
    finally { setBusy(false); }
  }

  return <main className="page-shell">
    <header className="page-header"><p className="eyebrow">Platform operations</p><h1>SaaS administration</h1><p>Global client, subscription, package and usage visibility. Access is restricted by the server-side platform-admin email allowlist.</p><Link href="/dashboard">Return to workspace dashboard</Link></header>
    {error && <p className="notice" role="alert">{error}</p>}{notice && <p className="notice" role="status">{notice}</p>}
    {!overview && !error && <section className="card"><p>Loading protected platform summary…</p></section>}
    {overview && <>
      <section className="section" aria-labelledby="totals-title"><h2 id="totals-title">Platform totals</h2><div className="metric-grid">
        {Object.entries(overview.totals).map(([key,value]) => <article className="card" key={key}><p className="fine">{key.replaceAll("_"," ")}</p><p className="metric-value">{value.toLocaleString()}</p></article>)}
      </div></section>
      <section className="section" aria-labelledby="plans-title"><h2 id="plans-title">Package management</h2><p className="fine">Price IDs are shown only to authorized platform admins. Deleting a package is a soft-deactivation so billing history is retained.</p>
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
      <section className="section" aria-labelledby="clients-title"><h2 id="clients-title">Clients and usage</h2><p className="fine">Usage figures are persisted reservation counts, not inferred revenue. Showing up to 500 workspaces.{overview.clients_truncated ? " The list is truncated; use database reporting for older records." : ""}</p>
        <div className="card table-wrap"><table><thead><tr><th>Workspace</th><th>Owner email</th><th>Subscription</th><th>Billing period</th><th>Usage counts</th></tr></thead><tbody>{overview.clients.map(client=><tr key={client.workspace_id}><td>{client.workspace_name}<br/><span className="fine">{client.workspace_id}</span></td><td>{client.owner_email || "Owner not mapped"}</td><td>{client.subscription_status || "No subscription"}</td><td>{client.billing_period_starts_at ? new Date(client.billing_period_starts_at).toLocaleDateString() : "—"} – {client.billing_period_ends_at ? new Date(client.billing_period_ends_at).toLocaleDateString() : "—"}</td><td>Consumed: {client.usage_consumed}<br/>Reserved: {client.usage_reserved}<br/>Released: {client.usage_released}</td></tr>)}</tbody></table>{!overview.clients.length && <p>No workspaces were found.</p>}</div>
      </section>
      <section className="section" aria-labelledby="feature-usage-title"><h2 id="feature-usage-title">Usage by client and feature</h2>
        <div className="card table-wrap"><table><thead><tr><th>Workspace ID</th><th>Feature</th><th>Consumed</th><th>Reserved</th><th>Released</th></tr></thead><tbody>{overview.usage_by_feature.map((item,index)=><tr key={item.workspace_id + ":" + item.feature + ":" + index}><td>{item.workspace_id}</td><td>{item.feature}</td><td>{item.consumed}</td><td>{item.reserved}</td><td>{item.released}</td></tr>)}</tbody></table>{!overview.usage_by_feature.length && <p>No feature usage records yet.</p>}</div>
      </section>
      <section className="section" aria-labelledby="usage-history-title"><h2 id="usage-history-title">Recent usage history</h2><p className="fine">Latest 200 persisted reservation records; no prompts, credentials, or message bodies are exposed.</p>
        <div className="card table-wrap"><table><thead><tr><th>Created</th><th>Client</th><th>Feature</th><th>Status</th><th>Billing period</th><th>Reservation ID</th></tr></thead><tbody>{overview.recent_usage.map(item=><tr key={item.reservation_id}><td>{new Date(item.created_at).toLocaleString()}</td><td>{item.workspace_name || item.workspace_id}</td><td>{item.feature}</td><td>{item.status}</td><td>{item.billing_period_starts_at ? new Date(item.billing_period_starts_at).toLocaleDateString() : "—"} – {item.billing_period_ends_at ? new Date(item.billing_period_ends_at).toLocaleDateString() : "—"}</td><td>{item.reservation_id}</td></tr>)}</tbody></table>{!overview.recent_usage.length && <p>No usage history yet.</p>}</div>
      </section>
    </>}
  </main>;
}
