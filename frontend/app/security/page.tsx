import type { Metadata } from "next";
import { SiteHeader, SiteFooter } from "../components/site-chrome";
export const metadata: Metadata = { title: "Security", description: "Security principles and responsible account practices for the platform." };
const sections:[string,string][]=[
["Workspace isolation and authorization","Protected workspace actions are intended to be authorized on the server against the signed-in user and workspace role. Never assume a hidden button or client-side check is an access control."],
["Sessions and request protection","The application is designed to use secure session handling, request-origin checks and CSRF protection for state-changing actions. Keep your browser and account credentials protected."],
["Provider credentials","Customer provider credentials should be stored separately by workspace and protected at rest. Platform operational credentials are a separate scope. Credentials must not be exposed in browser responses, source control or logs."],
["Operational safeguards","Rate limits, audit records, secret redaction, dependency updates and controlled deployment practices help reduce risk. No system can promise absolute security."],
["Report a security concern","Please report suspected vulnerabilities through the support channel published by the operator. Include a concise description and reproduction steps, but do not include real credentials, personal data or exploit payloads that affect other users."],
["Transparency","This page describes security principles and intended safeguards, not a third-party certification or guarantee. Confirm the current deployment, controls and incident-response contact before making compliance claims."]
];
export default function SecurityPage(){return <><SiteHeader/><main id="main" className="wrap"><section className="page-head"><p className="eyebrow">Trust and protection</p><h1>Security at every layer.</h1><p className="lead">Account, workspace and provider controls are designed to keep access scoped and sensitive information protected.</p><p className="notice" role="note">No independent security certification is claimed. This page describes product safeguards and operating principles.</p></section><div className="cards policy-grid">{sections.map(([h,b])=><article className="card" key={h}><h2>{h}</h2><p>{b}</p></article>)}</div></main><SiteFooter/></>;}
