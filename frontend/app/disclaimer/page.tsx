import type { Metadata } from "next";
import { SiteHeader, SiteFooter } from "../components/site-chrome";
export const metadata: Metadata = { title: "Disclaimer", description: "Important limitations of research, AI-generated recommendations and analytics." };
const sections:[string,string][]=[
["Research and AI outputs","Public-source research, extracted information and AI-generated text may be incomplete, outdated or inaccurate. Check original sources and independently verify material facts before relying on a recommendation or contacting anyone."],
["No professional advice","The service does not provide legal, financial, tax, compliance or other regulated professional advice. Obtain qualified advice for your circumstances and jurisdictions."],
["No guaranteed outcomes","The platform does not guarantee search rankings, traffic, AI citations, response rates, inbox placement, conversions, revenue or return on investment. Outcomes depend on many factors outside the service's control."],
["User responsibility","You are responsible for your use of prospect data, lawful basis and consent where required, message content, recipient eligibility, provider terms, opt-outs and approvals. A send attempt is not proof of delivery."],
["Availability and third parties","Features may depend on external providers, account eligibility, configuration and service availability. Provider terms and decisions may change independently."]
];
export default function DisclaimerPage(){return <><SiteHeader/><main className="wrap"><section className="page-head"><p className="eyebrow">Important information</p><h1>Disclaimer</h1><p className="lead">Understand the limits of automated research, generated content and performance reporting.</p></section><div className="cards policy-grid">{sections.map(([h,b])=><article className="card" key={h}><h2>{h}</h2><p>{b}</p></article>)}</div></main><SiteFooter/></>;}
