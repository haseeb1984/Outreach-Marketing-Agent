import Link from "next/link";
import { SiteHeader, SiteFooter } from "../components/site-chrome";

export const metadata = {
  title: "Frequently asked questions",
  description: "Answers about prospect research, outreach approvals, provider connections, analytics and billing.",
};

const qa = [
  ["Does the platform send messages automatically?", "Outreach drafts start in a pending-review state. An authorized workspace admin must approve a draft before it can be queued for email delivery. Email delivery also depends on a configured workspace SMTP account, server scheduler and usage entitlement; SMTP acceptance is not proof of inbox delivery."],
  ["Where does prospect information come from?", "The current research endpoint searches the public web through a configured Brave Search provider. Results include source URLs and lexical query-overlap hints, are deduplicated by hostname, and are not automatically saved or verified leads. Review and qualify each result before using it."],
  ["Is a sent message the same as delivered?", "No. The email analytics count records marked sent after the SMTP adapter accepts the send operation; this does not prove inbox delivery. Clicks, attributed signups, verified sales revenue and ROI are not currently available analytics metrics."],
  ["Can I connect my own email provider?", "Yes. Workspace owners and admins can configure their own supported SMTP account in workspace settings and test its connection. Platform operational email—such as account verification and password resets—uses a separate platform-owned configuration."],
  ["Can I use WhatsApp outreach?", "Not for outbound sending at present. Workspace account, consent and template eligibility controls exist, and eligible drafts may be queued, but outbound WhatsApp dispatch is disabled. A queued record does not mean a message was sent."],
  ["How does billing work?", "Paddle is the selected billing provider and the plan catalog reflects current configuration. Paid subscriptions and production checkout are not generally available until merchant eligibility, signed subscription events and the complete billing lifecycle are verified."],
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