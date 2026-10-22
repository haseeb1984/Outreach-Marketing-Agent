import Link from "next/link";

export const metadata = {
  title: "Privacy Policy",
  description: "How Outreach Marketing Agent handles account, workspace, prospect and outreach data.",
  robots: { index: true, follow: true },
};

const sections: [string, string][] = [
  ["Information the service may process", "Depending on features you use, the service may process account details such as your email address; workspace and team membership data; business and prospect information you submit or obtain from permitted public sources; campaign drafts, approvals, suppression choices and delivery records; provider connection metadata; support requests; and technical security and usage logs."],
  ["Why information is used", "Information is used to provide account and workspace features, organize research and campaigns, create drafts for review, operate approved integrations, enforce access and usage limits, prevent abuse, maintain security, provide support, and improve service reliability. Analytics should distinguish recorded application activity from provider-confirmed delivery or independently verified commercial outcomes."],
  ["Public prospect research", "The product is intended for relevant business research using permitted public sources. Users must not submit or collect private-account data through unauthorized means, bypass access controls, or use the service for unlawful, deceptive, or unwanted contact. Source evidence and observation dates should be retained where available."],
  ["Outreach, consent and suppression", "Drafts require human review by default. Users are responsible for having an appropriate lawful basis and required permissions for outreach in their jurisdictions and for following email, WhatsApp and provider policies. Opt-outs, suppression requests, negative replies, complaints and provider restrictions must be respected. WhatsApp functionality is limited to eligible use of the official WhatsApp Business Platform."],
  ["Service providers and integrations", "The service may process data through infrastructure, database, email-delivery, AI/search, analytics and payment providers when those integrations are configured and used. Each integration should receive only the information needed for its purpose. Payment details should be handled by the payment provider; this application is not intended to store raw card numbers or CVV."],
  ["Security and credentials", "Access controls, workspace authorization, secure sessions, rate limits and secret-redaction controls are intended to reduce risk. Provider credentials should be stored in protected server-side secret storage and never placed in source code or application logs. No internet service can guarantee absolute security."],
  ["Retention, export and deletion", "Information should be retained only as long as needed for the disclosed service, security, legal and operational purposes. Backups, audit records and billing records may require separate retention rules. Account export and deletion capabilities must be used where available; any exceptions and retention periods need to be confirmed in the deployed product before launch."],
  ["Your responsibilities and choices", "Keep account credentials secure, submit only information you are authorized to use, configure provider connections responsibly, review drafts before sending, and promptly honor contact preferences. Do not rely on robots.txt or other discovery controls to protect confidential information; private data must be protected by access controls."],
  ["Changes and launch review", "This page describes intended product practices and must be reviewed against the actual production data flows, providers, retention configuration and launch jurisdictions before the service accepts customers. It is not a substitute for jurisdiction-specific legal advice. Do not treat it as a guarantee that every described control is already deployed."],
];

export default function PrivacyPage() {
  return <>
    <header className="wrap topbar"><Link className="brand" href="/"><span className="mark" aria-hidden="true">O</span> Outreach Marketing Agent</Link><nav className="nav" aria-label="Main navigation"><Link href="/product">Product</Link><Link href="/pricing">Pricing</Link><Link href="/faq">FAQ</Link></nav></header>
    <main className="wrap"><section className="page-head"><p className="eyebrow">Privacy and data</p><h1>Privacy Policy</h1><p className="lead">A plain-language overview of the data this product is designed to handle and the safeguards that should govern it.</p><p className="notice" role="note">Pre-launch policy draft: verify the deployed data flows, providers, retention periods and applicable legal requirements before production use.</p></section>
      <div className="cards">{sections.map(([heading, body]) => <article className="card" key={heading}><h2>{heading}</h2><p>{body}</p></article>)}</div>
      <section className="section"><h2>Questions or data requests</h2><p>Use the support channel published by the service operator for privacy questions, data access requests, corrections or deletion requests. A verified support contact must be published before launch.</p><p className="fine">This page intentionally does not invent a support email address or claim that account export/deletion workflows are already available.</p></section>
    </main>
    <footer className="wrap"><p><Link href="/">Home</Link> · <Link href="/terms">Terms</Link> · <Link href="/faq">FAQ</Link></p></footer>
  </>;
}
