import type { Metadata } from "next";
import Link from "next/link";
import { SiteHeader, SiteFooter } from "../components/site-chrome";

export const metadata: Metadata = {
  title: "Features",
  description: "Explore prospect research, email and WhatsApp outreach workflows, competitor intelligence and analytics.",
};

const features: [string, string][] = [
  ["Prospect discovery", "Find relevant businesses and decision-makers from permitted public sources. Keep evidence, source URLs, observation dates and fit reasons alongside records."],
  ["Personalized outreach", "Prepare business-specific email drafts from available facts. Review recipients, content and eligibility before approving any send."],
  ["Competitor intelligence", "Compare public website structure, content coverage, search intent and technical signals to identify practical opportunities."],
  ["Campaign operations", "Organize prospects, drafts, approvals, schedules and delivery records in workspace-scoped workflows."],
  ["Workspace and account controls", "Separate client workspaces, roles and provider connections. Protected actions are checked by the backend."],
  ["Evidence-led analytics", "Separate queued, attempted and provider-confirmed activity. Conversion and revenue figures appear only when reliable data is connected."],
  ["Customer-owned WhatsApp integration", "Connect each workspace to its own eligible Meta Business Portfolio, WABA and business phone number. Customer credentials and conversations remain workspace-specific."],
];

export default function FeaturesPage() {
  return <>
    <SiteHeader />
    <main className="wrap">
      <section className="page-head">
        <p className="eyebrow">Platform capabilities</p>
        <h1>One workspace. A clearer growth workflow.</h1>
        <p className="lead">Research, outreach and improvement tools designed to keep evidence visible and decisions accountable.</p>
      </section>
      <section className="cards">
        {features.map(([title, body], index) => <article className="card" key={title}><div className="icon-box">{String(index + 1).padStart(2, "0")}</div><h2>{title}</h2><p>{body}</p></article>)}
      </section>
      <section className="section" id="whatsapp-requirements">
        <p className="eyebrow">Before you connect</p>
        <h2>WhatsApp Business Platform prerequisites</h2>
        <p className="lead">Every customer connects their own Meta business assets. The platform does not supply a shared customer-facing WhatsApp number.</p>
        <div className="cards">
          <article className="card">
            <h3>What your business needs</h3>
            <ul>
              <li>Your own Meta Business Portfolio.</li>
              <li>A WhatsApp Business Account (WABA) owned by or assigned to that portfolio.</li>
              <li>An eligible business phone number that you can verify and use with the WhatsApp Business Platform.</li>
              <li>Administrator or partner permissions to manage the business, WABA and phone-number assets.</li>
              <li>Acceptance of Meta's applicable terms, business policies and verification requirements.</li>
            </ul>
          </article>
          <article className="card">
            <h3>Messaging responsibilities</h3>
            <ul>
              <li>Obtain and retain the required recipient opt-in or other lawful permission before messaging.</li>
              <li>Use approved message templates when Meta's rules require them, including applicable business-initiated conversations outside the customer-service window.</li>
              <li>Honor opt-outs, blocks, complaints and workspace suppression records.</li>
              <li>Pay Meta's applicable messaging charges and taxes directly under your Meta account.</li>
              <li>Keep your business profile and account information accurate and compliant.</li>
            </ul>
          </article>
          <article className="card">
            <h3>What the platform configures</h3>
            <ul>
              <li>The platform maintains its Meta Developer App, App Secret, webhook verification token, Graph API version and webhook endpoint.</li>
              <li>You authorize your own WABA, Phone Number ID and access token during the workspace connection flow.</li>
              <li>Your integration credentials are stored for your workspace and are not shared with other customers.</li>
              <li>Your conversations and delivery history remain scoped to your workspace.</li>
            </ul>
          </article>
        </div>
        <p className="notice" role="note">Availability notice: WhatsApp outbound dispatch is currently disabled pending central Meta configuration, webhook and worker activation, provider acceptance testing and final safety verification. Connecting a customer account alone does not enable sending.</p>
        <p className="fine">Meta may impose additional verification, eligibility, number-migration or policy requirements depending on your business, country and account history. Check the current requirements in your Meta Business and WhatsApp Manager before onboarding.</p>
        <p><Link href="/faq">Read the WhatsApp setup and billing FAQs</Link></p>
      </section>
      <section className="section">
        <div className="callout">
          <div><h2>See how the workflow fits together</h2><p>Follow a prospect from discovery through human review and measured outcomes.</p></div>
          <Link className="button" href="/how-it-works">How it works</Link>
        </div>
      </section>
    </main>
    <SiteFooter />
  </>;
}
