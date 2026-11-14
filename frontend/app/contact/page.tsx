import Link from "next/link";
import { SiteHeader, SiteFooter } from "../components/site-chrome";

export const metadata = {
  title: "Contact support",
  description: "Find the right support route for Outreach Marketing Agent account, billing, privacy and product questions.",
  robots: { index: false, follow: false },
};

const resources = [
  { number: "01", title: "Account access", text: "Having trouble signing in or verifying your email? Start with the account recovery options.", href: "/forgot-password", link: "Recover account access" },
  { number: "02", title: "Product questions", text: "Find answers about prospect research, outreach approvals, connected providers and workspace controls.", href: "/faq", link: "Browse common questions" },
  { number: "03", title: "Billing and privacy", text: "Review plan information, billing terms and the current privacy notice before raising a request.", href: "/pricing", link: "Review plans and policies" },
];

export default function ContactPage() {
  const supportEmail = process.env.NEXT_PUBLIC_SUPPORT_EMAIL?.trim();
  const validSupportEmail = supportEmail && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(supportEmail) ? supportEmail : null;

  return <>
    <SiteHeader/>
    <main id="main" className="wrap contact-page">
      <section className="page-head contact-head">
        <p className="eyebrow">Support and enquiries</p>
        <h1>Let's get you to the right place.</h1>
        <p className="lead">Whether it is account access, a billing question or product guidance, use the route that best fits what you need.</p>
      </section>
      <section className="contact-support-panel">
        <div className="contact-support-copy">
          <span className="contact-kicker">DIRECT SUPPORT</span>
          <h2>Talk to the support team.</h2>
          <p>If a verified support address is published, use it for account-specific, billing or privacy requests. Its current availability is shown alongside this notice. Never include passwords, session cookies, verification links, full payment-card details or provider access tokens.</p>
        </div>
        <div className="contact-support-action">
          {validSupportEmail ? <><span className="contact-status">SUPPORT EMAIL PUBLISHED</span><a className="button" href={`mailto:${validSupportEmail}`}>Email support <span aria-hidden="true">↗</span></a><span className="contact-email">{validSupportEmail}</span></> : <><span className="contact-status contact-status-pending">SUPPORT CONTACT PENDING</span><p className="contact-pending">Direct email support is not configured yet. Use the self-service resources below while the service operator finalizes a verified support channel.</p></>}
        </div>
      </section>
      <section className="contact-resources">
        <div className="section-intro"><div><p className="eyebrow">Quick help</p><h2>Start with the right resource.</h2></div><p>These pages can help resolve common questions without sharing sensitive account or payment information.</p></div>
        <div className="cards">{resources.map(item=><article className="card contact-resource-card" key={item.number}><span className="contact-resource-number">{item.number}</span><h3>{item.title}</h3><p>{item.text}</p><Link href={item.href}>{item.link} <span aria-hidden="true">↗</span></Link></article>)}</div>
      </section>
      <p className="contact-privacy-note">For personal-data requests, review the <Link href="/privacy">Privacy Policy</Link>. A verified operator contact and the production data-handling details must be confirmed before launch.</p>
    </main>
    <SiteFooter/>
  </>;
}
