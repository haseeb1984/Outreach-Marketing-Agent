import Link from "next/link";
import { SiteHeader, SiteFooter } from "../components/site-chrome";

export const metadata = {
  title: "Contact support | Outreach Marketing Agent",
  description: "Find support options for Outreach Marketing Agent account, billing, privacy, and product questions.",
  robots: { index: false, follow: false },
};

export default function ContactPage() {
  const supportEmail = process.env.NEXT_PUBLIC_SUPPORT_EMAIL?.trim();
  const validSupportEmail = supportEmail && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(supportEmail) ? supportEmail : null;

  return <>
    <SiteHeader/>
    <main className="wrap"><article className="form-card" aria-labelledby="contact-title"><p className="eyebrow">We can help</p><h1 id="contact-title">Contact support</h1><p>If you need help with access, billing, privacy, or product behavior, start with the support route configured by the site operator.</p>
      {validSupportEmail ? <p>For support, email <a href={`mailto:${validSupportEmail}`}>{validSupportEmail}</a>. Please do not send passwords, session cookies, verification links, payment-card details, or provider access tokens.</p> : <p className="notice" role="status">A support email address has not been published on this site yet. Please use the FAQ for general questions or contact the service operator through your existing support channel.</p>}
      <h2>Helpful links</h2><ul><li><Link href="/faq">Frequently asked questions</Link></li><li><Link href="/pricing">Plans and pricing</Link></li><li><Link href="/privacy">Privacy notice and account-data questions</Link></li><li><Link href="/terms">Terms of service</Link></li><li><Link href="/forgot-password">Recover account access</Link></li></ul>
    </article></main>
    <SiteFooter/>
  </>;
}
