import Link from "next/link";

const primary = [
  ["/features", "Features"], ["/how-it-works", "How it works"],
  ["/pricing", "Pricing"], ["/about", "About"], ["/contact", "Contact"], ["/faq", "FAQ"],
] as const;
const legal = [
  ["/privacy", "Privacy"], ["/terms", "Terms"], ["/cookies", "Cookies"],
  ["/refunds", "Refunds"], ["/disclaimer", "Disclaimer"], ["/security", "Security"],
] as const;

function BrandMark() {
  return <span className="brand-symbol" aria-hidden="true"><svg viewBox="0 0 48 48"><defs><linearGradient id="mailmark" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#68b7ff"/><stop offset="1" stopColor="#1554df"/></linearGradient></defs><rect x="3" y="8" width="42" height="32" rx="8" fill="url(#mailmark)"/><path d="m6 13 18 14 18-14" fill="none" stroke="white" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round"/><path d="m6 36 13-12m23 12L29 24" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round"/><path d="M31 5 43 2l-3 12" fill="none" stroke="#8a75ff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/></svg></span>;
}
export function SiteHeader() {
  return <header className="site-header"><div className="wrap topbar">
    <Link className="brand" href="/" aria-label="Outreach Marketing Agent home"><BrandMark/><span className="brand-name">Outreach<small>Marketing Agent</small></span></Link>
    <nav className="nav" aria-label="Main navigation">{primary.map(([href,label])=><Link href={href} key={href}>{label}</Link>)}<Link className="security-nav" href="/security">♢ Security</Link><Link className="login-link" href="/login">Login</Link><Link className="button nav-cta" href="/register">Get started free <span aria-hidden="true">→</span></Link></nav>
  </div></header>;
}
export function SiteFooter() {
  return <footer className="site-footer"><div className="wrap">
    <div className="footer-columns">
      <div className="footer-about"><Link className="brand footer-brand" href="/"><BrandMark/><span className="brand-name">Outreach<small>Marketing Agent</small></span></Link><p>Smarter research. More thoughtful outreach. Better-informed growth.</p><div className="footer-social" aria-label="Social links"><span>in</span><span>𝕏</span><span>▶</span><span>⌘</span></div></div>
      <div><strong>Explore</strong><nav className="footer-links">{primary.map(([href,label])=><Link href={href} key={href}>{label}</Link>)}</nav></div>
      <div><strong>Legal & support</strong><nav className="footer-links">{legal.map(([href,label])=><Link href={href} key={href}>{label}</Link>)}</nav></div>
      <div><strong>Get started</strong><p>Bring your prospect research and outreach workflow together.</p><Link className="footer-start" href="/register">Create a workspace →</Link><Link href="https://juncsys.com" target="_blank" rel="noopener noreferrer">Junction Systems ↗</Link></div>
    </div>
    <div className="footer-bottom"><span>© {new Date().getFullYear()} Outreach Marketing Agent. All rights reserved.</span><span>Powered by <a href="https://juncsys.com" target="_blank" rel="noopener noreferrer">Junction Systems</a></span><span><Link href="/privacy">Privacy</Link> · <Link href="/terms">Terms</Link> · <Link href="/security">Security</Link></span></div>
    <p className="fine footer-disclaimer">Features and integrations are subject to availability, eligibility and verification. No ranking, delivery or revenue outcome is guaranteed.</p>
  </div></footer>;
}
