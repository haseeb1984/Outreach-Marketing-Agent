import type { Metadata } from "next";
import Link from "next/link";
import { SiteHeader, SiteFooter } from "../components/site-chrome";
export const metadata: Metadata = { title: "Features", description: "Explore prospect research, outreach workflows, competitor intelligence and analytics." };
const features = [
["Prospect discovery","Find relevant businesses and decision-makers from permitted public sources. Keep evidence, source URLs, observation dates and fit reasons alongside records."],
["Personalized outreach","Prepare business-specific email drafts from available facts. Review recipients, content and eligibility before approving any send."],
["Competitor intelligence","Compare public website structure, content coverage, search intent and technical signals to identify practical opportunities."],
["Campaign operations","Organize prospects, drafts, approvals, schedules and delivery records in workspace-scoped workflows."],
["Workspace and account controls","Separate client workspaces, roles and provider connections. Protected actions are checked by the backend."],
["Evidence-led analytics","Separate queued, attempted and provider-confirmed activity. Conversion and revenue figures appear only when reliable data is connected."]
];
export default function FeaturesPage(){return <><SiteHeader/><main className="wrap"><section className="page-head"><p className="eyebrow">Platform capabilities</p><h1>One workspace. A clearer growth workflow.</h1><p className="lead">Research, outreach and improvement tools designed to keep evidence visible and decisions accountable.</p></section><section className="cards feature-grid">{features.map(([title,body],i)=><article className="card" key={title}><div className="icon-box">{String(i+1).padStart(2,"0")}</div><h2>{title}</h2><p>{body}</p></article>)}</section><section className="section"><div className="callout"><div><h2>See how the workflow fits together</h2><p>Follow a prospect from discovery through human review and measured outcomes.</p></div><Link className="button" href="/how-it-works">How it works</Link></div></section></main><SiteFooter/></>;}
