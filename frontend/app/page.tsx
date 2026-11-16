import Link from "next/link";
import { SiteHeader, SiteFooter } from "./components/site-chrome";

const features = [
  { icon: "✦", title: "Evidence-led prospecting", body: "Discover relevant businesses with source-backed context, fit signals and deduplication." },
  { icon: "✉", title: "Personalized campaigns", body: "Create thoughtful outreach drafts grounded in prospect and business research." },
  { icon: "◎", title: "Competitor intelligence", body: "Review public positioning, content and technical signals to identify opportunities." },
  { icon: "↗", title: "Performance insights", body: "Understand recorded campaign activity and verified outcomes in one workspace." },
  { icon: "⚙", title: "Your SMTP, your control", body: "Connect and test your own sending provider before activating outreach." },
  { icon: "♢", title: "Responsible by design", body: "Human approval, suppression rules and opt-outs remain central to the workflow." },
];

const steps = [
  { n: "01", title: "Create your account", body: "Set up your account and workspace in a few straightforward steps." },
  { n: "02", title: "Configure your workspace", body: "Connect the services you use and research the prospects you want to reach." },
  { n: "03", title: "Review, launch and learn", body: "Prepare campaign drafts, approve messages and monitor recorded results." },
];

export default function HomePage() {
  return <><a className="skip" href="#main">Skip to main content</a><SiteHeader />
    <main id="main">
      <section className="home-hero"><div className="wrap home-hero-grid">
        <div className="home-hero-copy"><span className="hero-pill"><span>✦</span> Research • Personalize • Grow</span>
          <h1>Outreach Marketing Agent<span>Your smart outreach partner</span></h1>
          <p className="hero-description">Find the right prospects, create personalized campaigns and understand your results with an intelligent, evidence-led outreach workspace.</p>
          <div className="actions"><Link className="button hero-primary" href="/register">Get started free <span aria-hidden="true">→</span></Link><Link className="button hero-secondary" href="/how-it-works">Explore how it works <span aria-hidden="true">▷</span></Link></div>
          <div className="hero-assurances"><span>✓ Human approval by default</span><span>✦ Evidence-led research</span><span>⌁ Your sending accounts</span></div>
        </div>
        <div className="dashboard-art" aria-label="Illustration of an outreach analytics workspace">
          <div className="art-orbit orbit-one"></div><div className="art-orbit orbit-two"></div>
          <div className="mock-window"><div className="mock-top"><span className="mini-brand"><span className="mini-mark">✉</span> Outreach <small>Marketing Agent</small></span><span className="mock-dots">● ● ●</span></div>
            <div className="mock-body"><aside className="mock-sidebar"><b>▦ &nbsp; Overview</b><span>✉ &nbsp; Campaigns</span><span>♙ &nbsp; Prospects</span><span>◷ &nbsp; Analytics</span><span>⚙ &nbsp; Settings</span></aside>
              <div className="mock-content"><div className="mock-heading"><div><b>Workspace overview</b><small>Your outreach at a glance</small></div><span className="period-chip">Last 30 days⌄</span></div>
                <div className="mock-metrics"><div><i>✉</i><small>Campaigns</small><b>In control</b><em>Drafts & activity</em></div><div><i>♙</i><small>Prospects</small><b>Organized</b><em>Research-backed</em></div><div><i>◎</i><small>Insights</small><b>Actionable</b><em>Recorded results</em></div></div>
                <div className="mock-chart"><div className="chart-title"><b>Campaign activity</b><span><i></i> Activity <i></i> Engagement</span></div><svg viewBox="0 0 520 150" role="img" aria-label="Illustrative campaign activity trend"><path d="M0 118 C45 105 55 45 105 70 S165 115 215 65 275 25 320 58 385 100 430 48 485 40 520 18" fill="none" stroke="#1767ed" strokeWidth="4" strokeLinecap="round"/><path d="M0 132 C55 120 70 95 115 108 S180 125 220 95 280 82 325 100 390 115 430 90 485 82 520 65" fill="none" stroke="#9c78f5" strokeWidth="3" strokeLinecap="round"/><path d="M0 140H520" stroke="#e7edf7" strokeWidth="1"/></svg></div>
              </div>
            </div>
          </div><div className="floating-note"><span>✦</span><div><b>Research to outreach</b><small>One connected workflow</small></div></div><div className="floating-plane" aria-hidden="true">➤</div>
        </div>
      </div></section>
      <section className="wrap feature-band" aria-label="Platform benefits">{features.slice(0,3).map(f=><div className="benefit" key={f.title}><span>{f.icon}</span><div><b>{f.title}</b><small>{f.body}</small></div></div>)}</section>
      <section className="section wrap home-features"><div className="section-intro"><span className="section-kicker">Everything in one workspace</span><h2>Tools to make every conversation count</h2><p>Bring research, personalization, sending setup and performance insights together in a workflow you control.</p></div><div className="home-feature-grid">{features.map(f=><article className="home-feature-card" key={f.title}><span className="feature-icon">{f.icon}</span><h3>{f.title}</h3><p>{f.body}</p></article>)}</div><p className="section-link"><Link href="/features">Explore all features <span aria-hidden="true">→</span></Link></p></section>
      <section className="steps-section"><div className="wrap"><div className="section-intro"><span className="section-kicker">Simple by design</span><h2>Get started in three simple steps</h2><p>Move from account setup to informed outreach with a clear, reviewable process.</p></div><div className="home-steps">{steps.map((s,i)=><article className="home-step" key={s.n}><span className="step-bubble">{s.n}</span>{i!==2&&<span className="step-connector" aria-hidden="true">→</span>}<h3>{s.title}</h3><p>{s.body}</p></article>)}</div><div className="steps-cta"><Link className="button" href="/how-it-works">View the detailed guide <span aria-hidden="true">→</span></Link></div></div></section>
      <section className="section wrap home-pricing"><div className="section-intro"><span className="section-kicker">Flexible plans</span><h2>A plan for the way you grow</h2><p>Compare current plan features and workspace limits before choosing what fits.</p></div><div className="pricing-preview"><article><span className="plan-label">Get started</span><h3>Free</h3><p>Explore the core workflow and set up your workspace.</p><Link href="/pricing">View free plan <span>→</span></Link></article><article className="featured-plan"><span className="popular-label">For growing teams</span><span className="plan-label">More capability</span><h3>Pro</h3><p>Unlock additional capacity and advanced workspace features.</p><Link href="/pricing">Compare Pro <span>→</span></Link></article><article><span className="plan-label">For organizations</span><h3>Business</h3><p>Review higher-capacity options and support for your organization.</p><Link href="/pricing">Explore plans <span>→</span></Link></article></div><p className="pricing-note">Plan availability, limits and prices are shown on the pricing page and may depend on account eligibility.</p></section>
      <section className="wrap trust-panel"><div><span className="section-kicker">Built around trust</span><h2>Growth with clarity and control.</h2><p>Know what was researched, review what will be sent, and distinguish recorded results from estimates. No fabricated testimonials or guaranteed outcomes.</p><Link href="/security">Learn about security <span>→</span></Link></div><div className="trust-points"><div><b>01</b><span>Source-aware research</span></div><div><b>02</b><span>Human-reviewed drafts</span></div><div><b>03</b><span>Transparent activity records</span></div></div></section>
      <section className="wrap final-cta"><div><span className="section-kicker">Ready when you are</span><h2>Build better outreach, one thoughtful step at a time.</h2><p>Create your workspace and take control of your prospect research and campaigns.</p></div><Link className="button" href="/register">Create your workspace <span>→</span></Link></section>
    </main><SiteFooter /></>;
}
