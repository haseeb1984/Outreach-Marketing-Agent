import Link from "next/link";
import { useId } from "react";

const primary = [
  ["/features", "Features"], ["/how-it-works", "How it works"],
  ["/pricing", "Pricing"], ["/about", "About"], ["/contact", "Contact"], ["/faq", "FAQ"],
] as const;
const legal = [
  ["/privacy", "Privacy"], ["/terms", "Terms"], ["/cookies", "Cookies"],
  ["/refunds", "Refunds"], ["/disclaimer", "Disclaimer"], ["/security", "Security"],
] as const;

export function BrandMark() {
  const gradientPrefix = `outreach-mark-${useId().replace(/:/g, "")}`;
  const gradientId = `${gradientPrefix}-gradient`;
  const accentId = `${gradientPrefix}-accent`;
  return <span className="brand-symbol" aria-hidden="true"><svg viewBox="0 0 64 64" role="img">
    <defs>
      <linearGradient id={gradientId} x1="8" y1="8" x2="56" y2="58" gradientUnits="userSpaceOnUse"><stop stopColor="#8B7BFF"/><stop offset=".46" stopColor="#168BFF"/><stop offset="1" stopColor="#0645C8"/></linearGradient>
      <linearGradient id={accentId} x1="19" y1="45" x2="44" y2="20" gradientUnits="userSpaceOnUse"><stop stopColor="#18D5E8"/><stop offset="1" stopColor="#4D70FF"/></linearGradient>
    </defs>
    <path d="M46.8 12.2A25 25 0 1 0 53 37.8" fill="none" stroke={`url(#${gradientId})`} strokeWidth="7" strokeLinecap="round"/>
    <path d="M48.7 7.8 59 6l-2.1 10.4" fill="none" stroke="#8874FF" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M14 43.5 23 37l7.2 4.5 9.3-13.2 7.4 4.1" fill="none" stroke={`url(#${accentId})`} strokeWidth="4.3" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M28.2 24.1 56 11.4 43.3 39.2l-5.7-9.4-9.4-5.7Z" fill={`url(#${gradientId})`} stroke="#fff" strokeWidth="1.6" strokeLinejoin="round"/>
    <path d="m28.2 24.1 9.4 5.7 18.4-18.4" fill="none" stroke="#BDEBFF" strokeWidth="1.8" strokeLinejoin="round"/>
    <circle cx="13.5" cy="15" r="2.2" fill="#A58CFF"/>
  </svg></span>;
}
function BrandLockup({ footer = false }: { footer?: boolean }) {
  return <Link className={`brand${footer ? " footer-brand" : ""}`} href="/" aria-label="Outreach Marketing Agent home"><BrandMark/><span className="brand-name">Outreach<small>Marketing Agent</small></span></Link>;
}
export function SiteHeader() {
  return <header className="site-header"><div className="wrap topbar">
    <BrandLockup/>
    <nav className="nav" aria-label="Main navigation">{primary.map(([href,label])=><Link href={href} key={href}>{label}</Link>)}<Link className="security-nav" href="/security">♢ Security</Link><Link className="login-link" href="/login">Login</Link><Link className="button nav-cta" href="/register">Create your account <span aria-hidden="true">→</span></Link></nav>
  </div></header>;
}
export function SiteFooter() {
  return <footer className="site-footer"><div className="wrap">
    <div className="footer-columns">
      <div className="footer-about"><BrandLockup footer/><p>Smarter research. More thoughtful outreach. Better-informed growth.</p></div>
      <div><strong>Explore</strong><nav className="footer-links">{primary.map(([href,label])=><Link href={href} key={href}>{label}</Link>)}</nav></div>
      <div><strong>Legal & support</strong><nav className="footer-links">{legal.map(([href,label])=><Link href={href} key={href}>{label}</Link>)}</nav></div>
      <div><strong>Get started</strong><p>Bring your prospect research and outreach workflow together.</p><Link className="footer-start" href="/register">Create a workspace →</Link><Link href="https://juncsys.com" target="_blank" rel="noopener noreferrer">Junction Systems ↗</Link></div>
    </div>
    <div className="footer-bottom"><span>© {new Date().getFullYear()} Outreach Marketing Agent. All rights reserved.</span><span>Powered by <a href="https://juncsys.com" target="_blank" rel="noopener noreferrer">Junction Systems</a></span><span><Link href="/privacy">Privacy</Link> · <Link href="/terms">Terms</Link> · <Link href="/security">Security</Link></span></div>
  </div></footer>;
}
