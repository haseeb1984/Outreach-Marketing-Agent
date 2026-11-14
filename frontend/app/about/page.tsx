import type { Metadata } from "next";
import Link from "next/link";
import { SiteHeader, SiteFooter } from "../components/site-chrome";

export const metadata: Metadata = {
  title: "About the platform",
  description: "The principles behind Outreach Marketing Agent: evidence-led research, human oversight and responsible business outreach.",
};

const principles = [
  { number: "01", title: "Evidence over assumptions", text: "Recommendations should be traceable to observable sources. When information is incomplete, uncertainty should be visible instead of filling gaps with invented facts." },
  { number: "02", title: "People stay in control", text: "Human review, explicit approvals and workspace permissions guide consequential actions. Preparing a draft is not the same as authorizing a send." },
  { number: "03", title: "Responsible by design", text: "Recipient eligibility, opt-outs, suppression choices, provider rules and secure account boundaries belong in the workflow—not as afterthoughts." },
];

export default function AboutPage() {
  return <>
    <SiteHeader/>
    <main id="main" className="wrap about-page">
      <section className="page-head about-hero">
        <p className="eyebrow">About the product</p>
        <h1>Better business growth starts with better evidence.</h1>
        <p className="lead">Outreach Marketing Agent brings prospect research, qualification, campaign preparation and website-growth analysis into one accountable workspace—so teams can make informed decisions without losing sight of the evidence.</p>
        <div className="actions"><Link className="button" href="/features">Explore the platform <span aria-hidden="true">↗</span></Link><Link className="button secondary" href="/how-it-works">See how it works</Link></div>
      </section>
      <section className="about-principles" aria-label="Product principles">
        <div className="section-intro"><div><p className="eyebrow">What guides the product</p><h2>Useful tools. Clear responsibility.</h2></div><p>Technology can organize research and remove repetitive work. The people using it remain responsible for the decisions that matter.</p></div>
        <div className="cards feature-grid">{principles.map(item=><article className="card about-principle" key={item.number}><span className="contact-resource-number">{item.number}</span><h3>{item.title}</h3><p>{item.text}</p></article>)}</div>
      </section>
      <section className="about-workflow">
        <div><p className="eyebrow">A connected approach</p><h2>From public signals to measured action.</h2></div>
        <p>Research helps identify relevant opportunities. Qualification adds context. Outreach preparation turns verified facts into drafts for review. Measurement then separates recorded activity from outcomes confirmed by connected providers or first-party data.</p>
        <Link href="/how-it-works">Explore the workflow <span aria-hidden="true">↗</span></Link>
      </section>
      <section className="section"><div className="callout"><div><h2>Built for practical, measurable work.</h2><p>We distinguish what the platform records from outcomes independently confirmed by connected providers or first-party data.</p></div><Link className="button" href="/register">Create a workspace</Link></div></section>
    </main>
    <SiteFooter/>
  </>;
}
