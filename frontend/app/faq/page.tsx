import Link from "next/link";
import { SiteHeader, SiteFooter } from "../components/site-chrome";

export const metadata = {
  title: "FAQ",
  description: "Frequently asked questions about prospect research, outreach controls, WhatsApp setup, analytics and billing.",
};

const qa: [string, string][] = [
  ["Does the platform send messages automatically?", "Outreach drafts require human review by default. Approving a draft is not the same as sending it. Any enabled send workflow remains subject to workspace permissions, recipient eligibility, provider rules, rate limits and suppression checks."],
  ["Where does prospect information come from?", "Research is limited to permitted public sources and should preserve source evidence and observation dates. The product must not scrape private accounts or bypass access controls."],
  ["Is a sent message the same as delivered?", "No. A recorded send attempt is not proof that a recipient inbox received a message. Delivery, clicks, conversions and revenue are shown only when supported by reliable provider or connected first-party data."],
  ["How does billing work?", "Paddle Billing is the selected provider. Paid access activates only after a signed, verified subscription event updates the server-side record. Production checkout is not available until the live Paddle account, approved prices, webhook and launch configuration have been verified."],
  ["Can I connect my own WhatsApp account?", "Yes. Each customer connects their own eligible Meta Business Portfolio, WhatsApp Business Account (WABA), business phone number and credentials. The platform does not provide a shared WhatsApp number. Credentials are stored against the customer's workspace, not shared with other customers."],
  ["What do I need before connecting WhatsApp?", "You need: (1) your own Meta Business Portfolio; (2) a WhatsApp Business Account (WABA) in that portfolio; (3) an eligible business phone number that you can verify and use with the WhatsApp Business Platform; (4) the required administrator or partner permissions to manage the business and WhatsApp assets; and (5) acceptance of Meta's applicable terms and policies. Meta may require additional business verification or eligibility checks depending on the account and country."],
  ["Do I need to provide my own WhatsApp API credentials?", "Yes. During onboarding, connect the Meta assets and authorize the required WhatsApp Business Platform access. The integration needs the customer's WABA, Phone Number ID and an authorized access token. The platform's Meta app and webhook configuration are managed centrally; customers should not be asked to invent or supply platform App Secret or webhook verification secrets."],
  ["Who pays WhatsApp messaging charges?", "Each customer is responsible for Meta's applicable WhatsApp Business Platform messaging charges and any taxes or charges imposed by Meta. Those charges are separate from any Outreach Marketing Agent subscription."],
  ["Can I message any phone number?", "No. You must have the appropriate permission or opt-in for the message and comply with applicable law and Meta policy. Business-initiated messages outside the permitted customer-service window generally require an approved WhatsApp message template. Opt-outs and suppression requests must always be respected."],
  ["Is WhatsApp outbound messaging live?", "WhatsApp account connection and inbound foundations are implemented, but outbound dispatch remains disabled until the platform's Meta app credentials, webhook verification, operational worker, provider acceptance tests and safety checks have been completed. Do not assume that connecting an account means outbound sending is active."],
  ["Can the platform guarantee better search rankings?", "No. It can help diagnose and prioritize evidence-backed improvements, then measure results over time. Rankings depend on the site, query, market and other factors outside the platform's control."],
];

export default function FAQPage() {
  return <>
    <SiteHeader />
    <main className="wrap">
      <section className="page-head">
        <p className="eyebrow">Help and clarity</p>
        <h1>Frequently asked questions</h1>
        <p className="lead">Straight answers about how the product works, what you need to connect your accounts, and what is not yet live.</p>
      </section>
      <section className="cards">
        {qa.map(([question, answer]) => <article className="card" key={question}><h2>{question}</h2><p>{answer}</p></article>)}
      </section>
      <section className="section">
        <div className="callout">
          <div><h2>Preparing to connect WhatsApp?</h2><p>Review the full account, permissions, consent and messaging requirements before starting setup.</p></div>
          <Link className="button" href="/features#whatsapp-requirements">WhatsApp requirements</Link>
        </div>
      </section>
    </main>
    <SiteFooter />
  </>;
}
