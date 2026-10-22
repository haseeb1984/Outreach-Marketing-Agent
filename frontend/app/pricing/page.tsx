"use client";
import Link from "next/link";
import { useEffect, useState } from "react";

type Plan = {
  id: string;
  name: string;
  description: string;
  display_price: string | null;
  currency: string | null;
  billing_interval: string | null;
  checkout_available: boolean;
};

export default function PricingPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/billing/paddle/plans", { credentials: "same-origin", cache: "no-store" })
      .then(async response => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error("The plan catalog is temporarily unavailable.");
        return data as { items?: Plan[] };
      })
      .then(data => { if (!cancelled) setPlans(data.items || []); })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : "The plan catalog is temporarily unavailable."); })
      .finally(() => { if (!cancelled) setLoaded(true); });
    return () => { cancelled = true; };
  }, []);

  return <>
    <header className="wrap topbar"><Link className="brand" href="/"><span className="mark" aria-hidden="true">O</span> Outreach Marketing Agent</Link><nav className="nav" aria-label="Main navigation"><Link href="/product">Product</Link><Link href="/faq">FAQ</Link><Link href="/login">Sign in</Link></nav></header>
    <main className="wrap"><section className="page-head"><p className="eyebrow">Plans and billing</p><h1>Transparent plans. Server-verified access.</h1><p className="lead">Plans are displayed from the server-side catalog. The browser cannot choose its own price, grant access, or override workspace entitlements.</p></section>
      {error && <p className="notice" role="alert">{error}</p>}
      {!loaded && <p className="fine" role="status" aria-live="polite">Loading configured plans…</p>}
      {loaded && !plans.length && <section className="card"><h2>Plans are being configured</h2><p>There are no server-configured plans to display yet. We will not invent prices or show a fake purchase button.</p><p className="fine">Checkout stays unavailable until valid Paddle price IDs and the server-side subscription lifecycle are configured.</p></section>}
      {!!plans.length && <section className="cards" aria-label="Available subscription plans">{plans.map(plan=><article className="card" key={plan.id}><p className="eyebrow">Workspace plan</p><h2>{plan.name}</h2><p>{plan.description || "Access and usage limits are controlled by the verified server-side subscription."}</p><p className="lead">{plan.display_price ? plan.display_price + (plan.currency ? " " + plan.currency : "") + (plan.billing_interval ? " / " + plan.billing_interval : "") : "Price not supplied for display"}</p><p className="fine">{plan.checkout_available ? "Checkout is configured on the server. Full launch still requires successful sandbox and production verification." : "Checkout is not enabled until server-side billing configuration is complete."}</p><Link className="button" href="/login">Sign in to continue</Link></article>)}</section>}
      <section className="section"><div className="callout"><div><h2>Paid access follows verified billing events</h2><p>A checkout redirect is not proof of payment. Workspace access changes only after the signed Paddle webhook is validated and the server updates subscription state.</p></div><Link className="button" href="/faq">Billing FAQ</Link></div></section>
    </main><footer className="wrap"><Link href="/">Home</Link> · <Link href="/faq">FAQ</Link> · <Link href="/terms">Terms</Link> · <Link href="/privacy">Privacy</Link></footer>
  </>;
}
