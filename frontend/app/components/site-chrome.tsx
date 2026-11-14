import Link from "next/link";

const primary = [
  ["/features", "Features"], ["/how-it-works", "How it works"],
  ["/pricing", "Pricing"], ["/about", "About"], ["/faq", "FAQ"], ["/contact", "Contact"],
] as const;
const legal = [
  ["/privacy", "Privacy"], ["/terms", "Terms"], ["/cookies", "Cookies"],
  ["/refunds", "Refunds"], ["/disclaimer", "Disclaimer"], ["/security", "Security"],
] as const;

export function SiteHeader() {
  return <header className="wrap topbar">
    <Link className="brand" href="/" aria-label="Outreach Marketing Agent home">
      <span className="brand-symbol" aria-hidden="true"><svg viewBox="0 0 40 40" role="img"><path d="M20 3.5 35.5 12.4v15.2L20 36.5 4.5 27.6V12.4L20 3.5Z" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinejoin="round"/><path d="M11.5 26V14h7.8c3.4 0 5.2 1.6 5.2 4.2s-1.8 4.1-5.2 4.1h-7.8m12.2-1.2 7 5" fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round"/><path d="M27.8 10.8 30 13l-2.2 2.2-2.2-2.2 2.2-2.2Z" fill="currentColor"/></svg></span>
      <span>Outreach Marketing Agent</span>
    </Link>
    <nav className="nav" aria-label="Main navigation">
      {primary.map(([href, label]) => <Link href={href} key={href}>{label}</Link>)}
      <Link href="/login">Sign in</Link><Link className="button" href="/register">Get started</Link>
    </nav>
  </header>;
}

export function SiteFooter() {
  return <footer className="wrap site-footer">
    <div className="footer-columns">
      <div className="footer-brand-block"><Link className="brand footer-brand" href="/" aria-label="Outreach Marketing Agent home"><span className="brand-symbol" aria-hidden="true"><svg viewBox="0 0 40 40" role="img"><path d="M20 3.5 35.5 12.4v15.2L20 36.5 4.5 27.6V12.4L20 3.5Z" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinejoin="round"/><path d="M11.5 26V14h7.8c3.4 0 5.2 1.6 5.2 4.2s-1.8 4.1-5.2 4.1h-7.8m12.2-1.2 7 5" fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round"/><path d="M27.8 10.8 30 13l-2.2 2.2-2.2-2.2 2.2-2.2Z" fill="currentColor"/></svg></span><span className="footer-brand-name">Outreach Marketing Agent</span></Link><p className="fine">Evidence-led prospect research, responsible outreach and practical growth insights.</p></div>
      <div><strong>Explore</strong><nav className="footer-links">{primary.map(([href,label])=><Link href={href} key={href}>{label}</Link>)}</nav></div>
      <div><strong>Policies</strong><nav className="footer-links">{legal.map(([href,label])=><Link href={href} key={href}>{label}</Link>)}</nav></div>
    </div>
    <div className="footer-bottom"><span>© {new Date().getFullYear()} Outreach Marketing Agent</span><span>Powered by <a href="https://juncsys.com" target="_blank" rel="noopener noreferrer">Junction Systems</a></span></div>
  </footer>;
}
