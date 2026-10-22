"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export default function InvitationAcceptance({ token }: { token: string }) {
  const router = useRouter();
  const [csrf, setCsrf] = useState("");
  const [sessionReady, setSessionReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/auth/me", { credentials: "same-origin", cache: "no-store" })
      .then(async response => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok || typeof data.csrf_token !== "string" || !data.csrf_token) {
          throw new Error("Sign in with the invited email address, then reopen the invitation link.");
        }
        if (!cancelled) {
          setCsrf(data.csrf_token);
          setSessionReady(true);
        }
      })
      .catch(error => {
        if (!cancelled) setMessage(error instanceof Error ? error.message : "Sign in first, then reopen the invitation link.");
      });
    return () => { cancelled = true; };
  }, []);

  async function accept() {
    if (!token || !csrf) return;
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch("/api/v1/workspaces/invitations/accept", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ token }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const details: Record<string, string> = {
          invitation_invalid_or_expired: "This invitation is invalid, expired or already used.",
          invitation_expired: "This invitation has expired. Ask the workspace admin to send a new one.",
          invitation_email_mismatch: "Sign in with the email address that received this invitation.",
          already_workspace_member: "This account is already a member of the workspace.",
          csrf_validation_failed: "Security check expired. Refresh this page and try again.",
        };
        throw new Error(details[typeof data.detail === "string" ? data.detail : ""] || "The invitation could not be accepted.");
      }
      setMessage("Invitation accepted. Opening your workspace…");
      router.replace("/dashboard");
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The invitation could not be accepted.");
    } finally {
      setBusy(false);
    }
  }

  return <>
    <header className="wrap topbar"><Link className="brand" href="/"><span className="mark" aria-hidden="true">O</span> Outreach Marketing Agent</Link></header>
    <main className="wrap"><section className="form-card" aria-labelledby="invite-title">
      <p className="eyebrow">Workspace invitation</p><h1 id="invite-title">Join a workspace</h1>
      {!token ? <p className="notice" role="alert">The invitation link is missing its token. Open the complete link from the invitation email.</p> : null}
      {message ? <p className="notice" role="status" aria-live="polite">{message}</p> : null}
      {!sessionReady && token ? <p className="fine">Checking your sign-in session…</p> : null}
      {sessionReady && token ? <button className="button" type="button" disabled={busy} onClick={accept}>{busy ? "Accepting invitation…" : "Accept invitation"}</button> : null}
      {!sessionReady && <p><Link href="/login">Sign in</Link> · <Link href="/register">Create account</Link></p>}
      <p className="fine">The invitation can only be accepted by the account matching the invited email address.</p>
    </section></main>
  </>;
}
