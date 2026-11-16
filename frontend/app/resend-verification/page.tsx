"use client";
import Link from "next/link";
import { SiteHeader, SiteFooter } from "../components/site-chrome";
import { FormEvent, useState } from "react";

export default function ResendVerificationPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch("/api/v1/auth/resend-verification", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof data.detail === "string" ? data.detail : "";
        if (detail === "too_many_requests") throw new Error("Too many requests. Please wait before trying again.");
        throw new Error("Verification email could not be requested. Please try again later.");
      }
      setSubmitted(true);
      setMessage(typeof data.message === "string" ? data.message : "If the account needs verification, an email will be sent.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not reach the account service.");
    } finally {
      setBusy(false);
    }
  }

  return <>
    <SiteHeader/>
    <main className="wrap auth-main"><section className="form-card auth-card" aria-labelledby="verification-title"><p className="eyebrow">Email verification</p><h1 id="verification-title">Resend verification email</h1><p className="fine">Enter your registration email. We will show a generic confirmation to protect account privacy.</p>
      <form onSubmit={submit}><div className="field"><label htmlFor="email">Email address</label><input id="email" name="email" type="email" autoComplete="email" maxLength={320} required value={email} onChange={event => setEmail(event.target.value)} /></div><button className="button" type="submit" disabled={busy}>{busy ? "Requesting…" : "Resend verification"}</button></form>
      {message && <p className="notice" role={submitted ? "status" : "alert"} aria-live="polite">{message}</p>}
      <p className="fine"><Link href="/login">Return to sign in</Link></p></section></main>
    <SiteFooter/>
  </>;
}
