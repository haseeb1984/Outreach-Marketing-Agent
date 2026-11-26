"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { SiteHeader, SiteFooter } from "../components/site-chrome";

export default function ResetPasswordPage() {
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [message, setMessage] = useState("Preparing your password reset…");
  const [busy, setBusy] = useState(false);
  const [complete, setComplete] = useState(false);

  useEffect(() => {
    const fragment = window.location.hash.startsWith("#") ? window.location.hash.slice(1) : "";
    const params = new URLSearchParams(fragment);
    const resetToken = params.get("token") || "";
    // Strip the bearer token from the visible URL and browser history before
    // rendering the form or making any network request.
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    if (resetToken.length < 32 || resetToken.length > 512) {
      setMessage("This password-reset link is missing or invalid. Request a new link to continue.");
      return;
    }
    setToken(resetToken);
    setMessage("Choose a new password with at least 12 characters.");
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || busy) return;
    if (password.length < 12 || password.length > 1024) {
      setMessage("Your new password must contain at least 12 characters.");
      return;
    }
    if (password !== confirmation) {
      setMessage("The password confirmation does not match.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch("/api/v1/auth/password-reset/confirm", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: password }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof data.detail === "string" ? data.detail : "";
        const friendly: Record<string, string> = {
          password_reset_link_invalid_or_expired: "This password-reset link is invalid, expired, or already used. Request a new link.",
          too_many_requests: "Too many attempts. Please wait before trying again.",
        };
        throw new Error(friendly[detail] || "Password reset is temporarily unavailable. Please try again shortly.");
      }
      setComplete(true);
      setToken("");
      setPassword("");
      setConfirmation("");
      setMessage(typeof data.message === "string" ? data.message : "Your password has been updated. Sign in with your new password.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Password reset is temporarily unavailable.");
    } finally {
      setBusy(false);
    }
  }

  return <>
    <SiteHeader/>
    <main className="wrap auth-main">
      <section className="form-card auth-card" aria-labelledby="reset-title">
        <p className="eyebrow">Account recovery</p>
        <h1 id="reset-title">Choose a new password</h1>
        {token && !complete ? <form onSubmit={submit}>
          <div className="field"><label htmlFor="password">New password</label><input id="password" name="password" type="password" autoComplete="new-password" minLength={12} maxLength={1024} required value={password} onChange={event => setPassword(event.target.value)}/></div>
          <div className="field"><label htmlFor="confirmation">Confirm new password</label><input id="confirmation" name="confirmation" type="password" autoComplete="new-password" minLength={12} maxLength={1024} required value={confirmation} onChange={event => setConfirmation(event.target.value)}/></div>
          <button className="button" type="submit" disabled={busy}>{busy ? "Updating password…" : "Update password"}</button>
        </form> : null}
        <p className="notice" role="status" aria-live="polite">{message}</p>
        {complete ? <Link className="button" href="/login">Continue to sign in</Link> : !token ? <p className="fine"><Link href="/forgot-password">Request another reset link</Link></p> : null}
      </section>
    </main>
    <SiteFooter/>
  </>;
}
