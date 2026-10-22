import Link from "next/link";

export const metadata = {
  title: "Terms of Use",
  description: "Terms for responsible use of Outreach Marketing Agent.",
  robots: { index: true, follow: true },
};

const sections: [string, string][] = [
  ["Service status and changes", "Outreach Marketing Agent provides tools intended to support business research, prospect qualification, draft outreach, campaign organization and website-growth analysis. Features, integrations and availability may vary by deployment and may change. A capability described in marketing material is not a promise that its integration is enabled for your account."],
  ["Account and workspace security", "Provide accurate account information, protect credentials, and use only workspaces and provider accounts you are authorized to access. You are responsible for actions performed by your account and for promptly reporting suspected unauthorized access through the operator's published support channel."],
  ["Lawful and respectful use", "Use the service only for legitimate, relevant business purposes and in compliance with applicable laws, privacy obligations, anti-spam rules, platform terms and provider policies. Do not use it to harass, deceive, impersonate, send unlawful bulk messages, scrape private accounts, bypass access controls, evade rate limits or contact people after an applicable opt-out or suppression request."],
  ["Research evidence and AI-generated content", "Research and AI-generated recommendations may be incomplete or mistaken. Check source URLs, facts, relevance, recipient eligibility and message content before relying on them. Do not treat an inferred fact as verified. You remain responsible for the content and decisions you approve."],
  ["Human approval and external actions", "Outreach drafts are intended to require human review by default. Creating or approving a draft is distinct from queueing or sending it. Sending, paid transactions, account connections and any future automated action may require separate authorization, eligibility checks, provider configuration and explicit confirmation. Never assume a message was delivered merely because the application records a send attempt."],
  ["Third-party providers and billing", "Email, WhatsApp, search, AI, hosting and payment functionality may depend on third-party services and their eligibility rules. WhatsApp use must be through the official WhatsApp Business Platform where eligible. Paid access must be based on verified server-side subscription state, not a browser redirect. Do not rely on a displayed plan or price until the deployed billing catalog and checkout have been verified."],
  ["Your content and permissions", "You must have the rights and permissions needed to submit websites, repository data, prospect information, contact details, messages and other content. You authorize processing of that content only as needed to provide the features you choose and subject to the applicable privacy notice and configured integrations."],
  ["Availability, results and limitations", "The service is provided subject to availability and applicable law. No specific ranking position, traffic increase, AI-search citation, delivery rate, conversion, revenue or return on investment is guaranteed. Reports should distinguish observed evidence, recommendations and outcomes that have actually been verified."],
  ["Suspension and termination", "Access may be restricted where necessary to protect users, providers, the service or legal compliance. Account closure, export, deletion, billing cancellation and retention of records must follow the actual deployed policies and applicable legal obligations; confirm these procedures before relying on them."],
  ["Pre-launch review", "These terms are a product draft and require review by a qualified professional for the operator's legal entity, governing law, jurisdictions served, consumer and business rules, liability provisions, refunds, taxes, dispute resolution and support details. They do not replace legal advice and must not be treated as finalized terms until approved and published by the operator."],
];

export default function TermsPage() {
  return <>
    <header className="wrap topbar"><Link className="brand" href="/"><span className="mark" aria-hidden="true">O</span> Outreach Marketing Agent</Link><nav className="nav" aria-label="Main navigation"><Link href="/product">Product</Link><Link href="/pricing">Pricing</Link><Link href="/faq">FAQ</Link></nav></header>
    <main className="wrap"><section className="page-head"><p className="eyebrow">Responsible use</p><h1>Terms of Use</h1><p className="lead">Rules for using research, outreach, integrations and analytics responsibly.</p><p className="notice" role="note">Pre-launch terms draft: operator identity, governing law, refund/cancellation rules and other jurisdiction-specific clauses require review before production billing.</p></section>
      <div className="cards">{sections.map(([heading, body]) => <article className="card" key={heading}><h2>{heading}</h2><p>{body}</p></article>)}</div>
    </main>
    <footer className="wrap"><p><Link href="/">Home</Link> · <Link href="/privacy">Privacy</Link> · <Link href="/faq">FAQ</Link></p></footer>
  </>;
}
