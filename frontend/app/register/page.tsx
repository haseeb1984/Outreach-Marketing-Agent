"use client";
import Link from "next/link";
import { FormEvent, useState } from "react";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    setSuccess(false);
    try {
      const response = await fetch("/api/v1/auth/register", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof data.detail === "string" ? data.detail : "";
        const friendly: Record<string, string> = {
          authentication_not_configured: "Registration is temporarily unavailable. Please try again later.",
          too_many_requests: "Too many attempts. Wait a little before trying again.",
          request_origin_rejected: "This website is not yet authorized by the account service.",
          email_delivery_not_configured: "Account verification email is not configured yet.",
        };
        throw new Error(friendly[detail] || "Registration could not be completed. Check the details or try again later.");
      }
      setSuccess(true);
      setMessage(typeof data.message === "string" ? data.message : "If the address is eligible, a verification email will be sent.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not reach the account service.");
    } finally {
      setBusy(false);
    }
  }

  return <>
    <header className="wrap topbar"><Link className="brand" href="/"><span className="mark" aria-hidden="true">O</span> Outreach Marketing Agent</Link><nav className="nav" aria-label="Main navigation"><Link href="/product">Product</Link><Link href="/pricing">Pricing</Link><Link href="/login">Sign in</Link></nav></header>
    <main className="wrap"><section className="form-card" aria-labelledby="register-title"><p className="eyebrow">Create an account</p><h1 id="register-title">Start with your workspace</h1><p className="fine">Use a unique password with at least 12 characters. You must verify your email before signing in.</p>
      <form onSubmit={submit}><div className="field"><label htmlFor="email">Work email</label><input id="email" name="email" type="email" autoComplete="email" maxLength={320} required value={email} onChange={event => setEmail(event.target.value)} /></div>
      <div className="field"><label htmlFor="password">Password</label><input id="password" name="password" type="password" autoComplete="new-password" minLength={12} maxLength={1024} required value={password} onChange={event => setPassword(event.target.value)} /></div>
      <button className="button" type="submit" disabled={busy}>{busy ? "Submitting…" : "Create account"}</button></form>
      {message && <p className="notice" role={success ? "status" : "alert"} aria-live="polite">{message}</p>}
      <p className="fine">By creating an account, you acknowledge the <Link href="/terms">Terms</Link> and <Link href="/privacy">Privacy notice</Link>.</p>
      <p className="fine">Already registered? <Link href="/login">Sign in</Link></p></section></main>
    <footer className="wrap"><Link href="/">Home</Link> · <Link href="/faq">FAQ</Link></footer>
  </>;
}
