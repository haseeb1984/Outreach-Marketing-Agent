"use client";
import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch("/api/v1/auth/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof data.detail === "string" ? data.detail : "";
        const friendly: Record<string, string> = {
          authentication_not_configured: "Account service is not configured yet. Please try again later.",
          email_or_password_incorrect: "Email or password was not accepted.",
          email_not_verified: "Please verify your email before signing in.",
          invalid_credentials: "Email or password was not accepted.",
          too_many_requests: "Too many attempts. Wait a little before trying again.",
          request_origin_rejected: "This website is not yet authorized by the account service.",
        };
        throw new Error(friendly[detail] || "Sign-in could not be completed. Check your details or try again later.");
      }
      router.replace("/dashboard");
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not reach the account service.");
    } finally {
      setBusy(false);
    }
  }

  return <>
    <header className="wrap topbar"><Link className="brand" href="/"><span className="mark" aria-hidden="true">O</span> Outreach Marketing Agent</Link><nav className="nav" aria-label="Main navigation"><Link href="/product">Product</Link><Link href="/pricing">Pricing</Link><Link href="/register">Create account</Link></nav></header>
    <main className="wrap"><section className="form-card" aria-labelledby="login-title"><p className="eyebrow">Welcome back</p><h1 id="login-title">Sign in to your workspace</h1><p className="fine">Your session is handled by the backend through a same-origin secure connection.</p>
      <form onSubmit={submit}><div className="field"><label htmlFor="email">Email address</label><input id="email" name="email" type="email" autoComplete="email" maxLength={320} required value={email} onChange={event => setEmail(event.target.value)} /></div>
      <div className="field"><label htmlFor="password">Password</label><input id="password" name="password" type="password" autoComplete="current-password" maxLength={1024} required value={password} onChange={event => setPassword(event.target.value)} /></div>
      <button className="button" type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button></form>
      {message && <p className="notice" role="alert">{message}</p>}
      <p className="fine">New here? <Link href="/register">Create an account</Link></p></section></main>
    <footer className="wrap"><Link href="/">Home</Link> · <Link href="/faq">FAQ</Link></footer>
  </>;
}
