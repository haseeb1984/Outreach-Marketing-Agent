import type { Metadata } from "next";
import { SiteHeader, SiteFooter } from "../components/site-chrome";
export const metadata: Metadata = { title: "About", description: "The principles behind Outreach Marketing Agent." };
export default function AboutPage() { return <><SiteHeader/><main className="wrap">
  <section className="page-head"><p className="eyebrow">About the product</p><h1>Better business growth starts with better evidence.</h1><p className="lead">Outreach Marketing Agent brings research, prospect qualification, campaign preparation and website-growth analysis into one accountable workspace.</p></section>
  <section className="cards">
    <article className="card"><h2>Evidence over assumptions</h2><p>Recommendations should be traceable to observable sources, with uncertainty made clear instead of filling gaps with invented facts.</p></article>
    <article className="card"><h2>People stay in control</h2><p>Human review, explicit approvals and workspace permissions guide consequential actions. A draft is never presented as a delivered message.</p></article>
    <article className="card"><h2>Responsible by design</h2><p>Opt-outs, suppression choices, provider eligibility and security controls are part of the workflow—not optional afterthoughts.</p></article>
  </section>
  <section className="section"><div className="callout"><div><h2>Built for practical, measurable work</h2><p>We distinguish what the platform records from outcomes independently confirmed by connected providers or first-party data.</p></div><a className="button" href="/features">Explore features</a></div></section>
</main><SiteFooter/></>; }
