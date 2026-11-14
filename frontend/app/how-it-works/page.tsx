import type { Metadata } from "next";
import Link from "next/link";
import { SiteHeader, SiteFooter } from "../components/site-chrome";
export const metadata: Metadata = { title: "How it works", description: "How research, review, outreach and measurement work together." };
const steps = [
["01","Create a workspace","Set up your account, invite the right teammates and keep each client's research and connected accounts separated."],
["02","Research and qualify","Discover relevant prospects and competitors. Review source evidence, dates and fit signals before adding records to a campaign."],
["03","Prepare and approve","Create tailored drafts from available facts. Check recipient eligibility, message accuracy and suppression status, then approve actions explicitly."],
["04","Connect and measure","Configure your own provider account, test its connection and review recorded activity. Treat delivery and conversions as confirmed only when provider data supports them."]
];
export default function HowItWorksPage(){return <><SiteHeader/><main className="wrap"><section className="page-head"><p className="eyebrow">A transparent process</p><h1>From first signal to a thoughtful conversation.</h1><p className="lead">A straightforward workflow that keeps the research, approval and outcome stages distinct.</p></section><section className="steps-list">{steps.map(([number,title,body])=><article className="step-row" key={number}><span className="step-number">{number}</span><div><h2>{title}</h2><p>{body}</p></div></article>)}</section><section className="section"><div className="callout"><div><h2>Your provider account stays yours</h2><p>Customers configure their own workspace SMTP account for outreach. Platform system email is a separate operational service.</p></div><Link className="button" href="/register">Create your workspace</Link></div></section></main><SiteFooter/></>;}
