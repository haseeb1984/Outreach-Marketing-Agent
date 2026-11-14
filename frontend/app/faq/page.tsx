import Link from "next/link";
import { SiteHeader, SiteFooter } from "../components/site-chrome";

export const metadata = {
  title: "Frequently asked questions",
  description: "Answers about prospect research, outreach approvals, provider connections, analytics and billing.",
};

const qa = [
  ["Does the platform send messages automatically?", "Outreach drafts require human review by default. Any enabled sending workflow remains subject to explicit approval, recipient eligibility, provider rules, rate limits and suppression checks."],
  ["Where does prospect information come from?", "Research is based on permitted public sources. Source evidence, URLs and observation dates should remain visible so your team can check relevance before using a record."],
  ["Is a sent message the same as delivered?", "No. A send attempt is not proof that a recipient inbox received a message. Delivery, clicks, conversions and revenue are shown as confirmed only when reliable provider or connected first-party data supports them."],
  ["Can I connect my own email provider?", "Yes. Workspace owners can configure their own supported SMTP account in workspace settings. Platform operational email—such as account verification and password resets—uses a separate platform-owned configuration."],
  ["Can I use WhatsApp outreach?", "Only through the official WhatsApp Business Platform when account, recipient, consent and message eligibility meet applicable provider rules. Availability depends on completed onboarding and authorization."],
  ["How does billing work?", "Paddle is the selected billing provider. Workspace access must follow signed, verified server-side subscription events. The live plan catalog and checkout availability are determined by the current platform configuration."],
  ["Can the platform guarantee better search rankings?", "No. The platform can help diagnose and prioritize evidence-backed improvements, then measure observable changes over time. Rankings depend on many factors outside the service's control."],
  ["How do I contact support or request a refund?", "The Contact page shows whether the service operator has published a verified support channel. Until one is available, this website cannot receive support or refund requests. Review the Refund Policy for the current pre-launch status. Never send passwords, session cookies, full payment-card details or provider access tokens."],
];

export default function FAQPage() {
  return <>
    <SiteHeader/>
    <main id="main" className="wrap">
      <section className="page-head">
        <p className="eyebrow">Help and clarity</p>
        <h1>Questions, answered clearly.</h1>
        <p className="lead">Straight answers about the research, outreach and account workflows—without promising features or outcomes that have not been verified.</p>
      </section>
      <section className="faq-list" aria-label="Frequently asked questions">
        {qa.map(([question, answer], index) => <details className="faq-item" key={question}>
          <summary><span className="faq-number">{String(index + 1).padStart(2, "0")}</span><span>{question}</span><i aria-hidden="true">+</i></summary>
          <div className="faq-answer"><p>{answer}</p></div>
        </details>)}
      </section>
      <section className="section">
        <div className="callout"><div><h2>Still need a hand?</h2><p>Check the product guides and visit Contact to see whether a verified support channel is available.</p></div><Link className="button" href="/contact">Contact support</Link></div>
      </section>
    </main>
    <SiteFooter/>
  </>;
}
