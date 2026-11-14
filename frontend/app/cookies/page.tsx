import type { Metadata } from "next";
import { SiteHeader, SiteFooter } from "../components/site-chrome";
export const metadata: Metadata = { title: "Cookie Notice", description: "Information about cookies and browser storage used by the service." , robots: { index: false, follow: false }};
const sections:[string,string][]=[
["Essential session technologies","The application may use strictly necessary cookies or similar browser storage to maintain sign-in sessions, protect requests and support core account functionality. These technologies are required for the service features you request."],
["Preferences and diagnostics","Depending on the deployed configuration, the service may use limited preferences or diagnostic technologies to remember settings, understand reliability and protect the platform. Optional analytics or advertising cookies should not be enabled without the required notice and consent."],
["Third-party services","Embedded or connected providers may set their own technologies when you choose to use those services. Their handling is governed by their own notices and settings."],
["Your choices","You can manage or clear cookies through your browser. Blocking essential session cookies may prevent sign-in or other protected functions from working."],
["Configuration and review","This notice must be checked against the actual production cookie inventory, domains, lifetimes and consent tooling before launch. It does not claim that optional analytics or advertising cookies are currently deployed."]
];
export default function CookiesPage(){return <><SiteHeader/><main id="main" className="wrap"><section className="page-head"><p className="eyebrow">Browser technologies</p><h1>Cookie Notice</h1><p className="lead">How essential cookies and similar technologies may support account security and site functionality.</p><p className="notice" role="note">Configuration review required: confirm the live cookie inventory and consent requirements before publication as a final policy.</p></section><div className="cards policy-grid">{sections.map(([h,b])=><article className="card" key={h}><h2>{h}</h2><p>{b}</p></article>)}</div></main><SiteFooter/></>;}
