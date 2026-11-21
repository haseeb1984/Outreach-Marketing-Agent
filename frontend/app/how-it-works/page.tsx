import type { Metadata } from "next";
import Link from "next/link";
import { BrandMark, SiteHeader, SiteFooter } from "../components/site-chrome";

export const metadata: Metadata = {
  title: "How it works",
  description: "Follow the Outreach Marketing Agent workflow from workspace setup to evidence-led outreach and measurement.",
};

const stages = [
  { number: "01", label: "Set up", title: "Create your workspace", body: "Create your account, establish a workspace and invite teammates with the right roles. Each client's research, campaigns and provider connections stay in its own workspace.", points: ["Workspace and team setup", "Role-based access", "Separate client data"] },
  { number: "02", label: "Research", title: "Find and qualify prospects", body: "Discover relevant businesses and review the available source evidence, observation dates and fit signals before a prospect enters a campaign.", points: ["Source-backed prospect records", "Fit and relevance review", "Duplicate-aware organization"] },
  { number: "03", label: "Approve", title: "Prepare thoughtful outreach", body: "Prepare personalized drafts from available facts. Review the recipient, message, permission and suppression status, then explicitly approve the action.", points: ["Fact-grounded drafts", "Human review before action", "Opt-out and suppression checks"] },
  { number: "04", label: "Measure", title: "Connect your provider and learn", body: "Connect and test your own sending provider, then review recorded campaign activity. Delivery and commercial outcomes are treated as confirmed only when supported by provider or first-party data.", points: ["Your own workspace SMTP", "Provider-backed delivery status", "Evidence-led performance insights"] },
];

export default function HowItWorksPage() {
  return <>
    <SiteHeader />
    <main className="wrap how-page">
      <section className="page-head how-hero">
        <p className="eyebrow">A clear, reviewable process</p>
        <h1>From first signal to a thoughtful conversation.</h1>
        <p className="lead">One connected workflow for research, preparation, approval and measurement—with people in control at every important step.</p>
        <div className="how-hero-meta"><span><BrandMark /> Research with evidence</span><span>Human approval</span><span>Measured activity</span></div>
      </section>

      <section className="how-flow" aria-label="Four stages of the workflow">
        <div className="how-flow-heading"><div><p className="eyebrow">The workflow</p><h2>Four stages. Clear decisions.</h2></div><p>Move forward when the evidence and approvals are ready—not just because an automation is available.</p></div>
        <div className="how-stage-grid">
          {stages.map((stage, index) => <article className="how-stage" key={stage.number}>
            <div className="how-stage-top"><span className="how-stage-number">{stage.number}</span><span className="how-stage-label">{stage.label}</span></div>
            <h3>{stage.title}</h3><p>{stage.body}</p>
            <ul>{stage.points.map(point => <li key={point}>{point}</li>)}</ul>
            {index < stages.length - 1 && <span className="how-stage-arrow" aria-hidden="true">→</span>}
          </article>)}
        </div>
      </section>

      <section className="how-control">
        <div className="how-control-mark"><BrandMark /></div>
        <div><p className="eyebrow">Your accounts stay yours</p><h2>Connect your own sending provider.</h2><p>Each customer configures and tests their own SMTP account inside their workspace. Platform system email is a separate operational service; it does not replace your customer-owned sending setup.</p></div>
        <Link className="button" href="/register">Create your workspace <span aria-hidden="true">→</span></Link>
      </section>

      <section className="how-next">
        <div><p className="eyebrow">Ready to get started?</p><h2>Build a workflow you can understand and control.</h2><p>Explore the platform capabilities or create your workspace to begin.</p></div>
        <div className="actions"><Link className="button" href="/register">Get started free</Link><Link className="button secondary" href="/features">Explore features</Link></div>
      </section>
    </main>
    <SiteFooter />
  </>;
}
