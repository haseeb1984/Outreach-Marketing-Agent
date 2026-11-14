import Link from "next/link";
import { SiteHeader, SiteFooter } from "./components/site-chrome";

const workflow = [
  { number: "01", title: "Discover", detail: "Find businesses that fit your market using public evidence." },
  { number: "02", title: "Qualify", detail: "Review sources, fit signals and contact eligibility." },
  { number: "03", title: "Engage", detail: "Prepare relevant messages and approve before sending." },
];
const capabilities = [
  { icon: "⌕", title: "Prospect intelligence", text: "Build a focused prospect list with source links, fit notes and transparent research signals." },
  { icon: "↗", title: "Thoughtful outreach", text: "Turn verified context into tailored drafts. Keep review, approval and sending as distinct steps." },
  { icon: "◎", title: "Competitor insights", text: "Understand public positioning, content and website signals to identify practical opportunities." },
  { icon: "⌁", title: "Growth analytics", text: "See recorded activity clearly and separate provider-confirmed outcomes from assumptions." },
];

function ProductPreview() {
  return <div className="product-preview" aria-label="Illustrative Outreach Marketing Agent workspace preview">
    <div className="preview-sidebar">
      <div className="preview-brand"><span className="preview-brand-mark">O</span><span>outreach<span className="preview-brand-muted">.ai</span></span></div>
      <span className="preview-side-label">WORKSPACE</span>
      <span className="preview-side-item active"><i>▦</i> Overview</span>
      <span className="preview-side-item"><i>⌕</i> Prospects</span>
      <span className="preview-side-item"><i>✉</i> Campaigns</span>
      <span className="preview-side-item"><i>◎</i> Research</span>
      <span className="preview-side-label preview-side-label-lower">MANAGE</span>
      <span className="preview-side-item"><i>⚙</i> Settings</span>
      <div className="preview-profile"><span className="preview-avatar">JD</span><span><b>Jordan Davis</b><small>Workspace owner</small></span></div>
    </div>
    <div className="preview-main">
      <div className="preview-topline"><span>Workspace overview</span><span className="preview-date">Last 30 days&nbsp;⌄</span></div>
      <div className="preview-heading"><div><small>MONDAY, YOUR NEXT OPPORTUNITY STARTS HERE</small><h3>Good morning, Jordan</h3><p>Your research and outreach at a glance.</p></div><span className="preview-live"><i/> Workspace active</span></div>
      <div className="preview-metrics">
        <div><small>Qualified prospects</small><b>248</b><em>↗ Research queue</em></div>
        <div><small>Drafts prepared</small><b>36</b><em>↗ Awaiting review</em></div>
        <div><small>Campaign activity</small><b>12</b><em>↗ In progress</em></div>
      </div>
      <div className="preview-lower">
        <div className="preview-chart"><div className="preview-card-head"><b>Research activity</b><small>Weekly overview</small></div><div className="preview-chart-area"><div className="preview-ylabels"><span>80</span><span>60</span><span>40</span><span>20</span></div><svg viewBox="0 0 420 112" role="img" aria-label="Illustrative upward trend line"><path d="M0 88 C30 84 38 60 70 67 S112 82 140 55 S182 59 210 42 S250 58 280 30 S330 43 350 20 S390 22 420 7" fill="none" stroke="#5578f5" strokeWidth="3" strokeLinecap="round"/><path d="M0 88 C30 84 38 60 70 67 S112 82 140 55 S182 59 210 42 S250 58 280 30 S330 43 350 20 S390 22 420 7 L420 112 L0 112Z" fill="url(#previewFill)" opacity=".55"/><defs><linearGradient id="previewFill" x1="0" x2="0" y1="0" y2="1"><stop stopColor="#5578f5"/><stop offset="1" stopColor="#5578f5" stopOpacity="0"/></linearGradient></defs></svg></div><div className="preview-xlabels"><span>Mon</span><span>Tue</span><span>Wed</span><span>Thu</span><span>Fri</span><span>Sat</span><span>Sun</span></div></div>
        <div className="preview-activity"><div className="preview-card-head"><b>Next actions</b><small>Review queue</small></div><div className="preview-task"><span className="preview-task-icon">⌕</span><span><b>Review prospect fit</b><small>8 new research records</small></span><i>›</i></div><div className="preview-task"><span className="preview-task-icon">✉</span><span><b>Approve email drafts</b><small>4 drafts need your review</small></span><i>›</i></div><div className="preview-task"><span className="preview-task-icon">◎</span><span><b>Check campaign results</b><small>2 updates available</small></span><i>›</i></div></div>
      </div>
      <div className="preview-footnote"><span><i/> Illustrative workspace preview</span><span>Human review stays in control</span></div>
    </div>
  </div>;
}

export default function HomePage() {
  return <>
    <a className="skip" href="#main">Skip to main content</a>
    <SiteHeader/>
    <main id="main">
      <section className="hero hero-premium">
        <div className="wrap">
          <div className="hero-copy">
            <p className="eyebrow"><span className="eyebrow-dot"/> RESEARCH-LED OUTREACH, ALL IN ONE PLACE</p>
            <h1>Make every business conversation <span>count.</span></h1>
            <p className="lead">Find the right prospects, understand the market and prepare outreach with evidence behind every decision.</p>
            <div className="actions"><Link className="button" href="/register">Build your workspace <span aria-hidden="true">↗</span></Link><Link className="button secondary" href="/how-it-works">Explore how it works</Link></div>
            <div className="hero-assurance"><span><i/> Evidence-led research</span><span><i/> Human-approved outreach</span><span><i/> Your provider accounts</span></div>
          </div>
          <ProductPreview/>
          <div className="hero-caption"><span>ONE WORKSPACE. A CLEARER GROWTH WORKFLOW.</span><span>Research&nbsp; / &nbsp;Review&nbsp; / &nbsp;Engage&nbsp; / &nbsp;Measure</span></div>
        </div>
      </section>
      <section className="trust-strip"><div className="wrap trust-strip-inner"><span>BUILT AROUND RESPONSIBLE GROWTH</span><p>Public evidence <b>·</b> Clear approvals <b>·</b> Transparent activity <b>·</b> Workspace control</p></div></section>
      <section className="section wrap home-capabilities">
        <div className="section-intro"><div><p className="eyebrow">A connected growth toolkit</p><h2>From first signal to the next opportunity.</h2></div><p>Replace scattered research and disconnected workflows with one practical workspace for finding, understanding and engaging the businesses that matter.</p></div>
        <div className="capability-grid">{capabilities.map((item,index)=><article className="capability-card" key={item.title}><div className="capability-top"><span className="capability-icon">{item.icon}</span><span>0{index+1}</span></div><h3>{item.title}</h3><p>{item.text}</p><Link href="/features" aria-label={`Explore ${item.title}`}>Explore capability <span aria-hidden="true">↗</span></Link></article>)}</div>
      </section>
      <section className="workflow-section"><div className="wrap"><div className="section-intro"><div><p className="eyebrow">A workflow you can trust</p><h2>Clarity at every step.</h2></div><p>Keep research, message preparation, approval and real-world outcomes distinct—so your team always knows what has happened and what needs attention.</p></div><div className="workflow-grid">{workflow.map((item)=><article className="workflow-card" key={item.number}><span>{item.number}</span><div><h3>{item.title}</h3><p>{item.detail}</p></div></article>)}</div></div></section>
      <section className="section wrap"><div className="closing-panel"><div><p className="eyebrow">Make your next move a smarter one</p><h2>Better conversations begin with better context.</h2><p>Start with a workspace built to keep evidence visible and consequential actions in your hands.</p></div><div className="closing-actions"><Link className="button" href="/register">Get started <span aria-hidden="true">↗</span></Link><Link href="/pricing">View plans</Link></div><div className="closing-orbit" aria-hidden="true"><span/><span/><span/></div></div></section>
    </main>
    <SiteFooter/>
  </>;
}
