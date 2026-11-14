"use client";

import Link from "next/link";
import { SiteHeader, SiteFooter } from "../components/site-chrome";
import { useEffect, useState } from "react";

type VerificationState = "checking" | "success" | "invalid" | "unavailable";

export default function VerifyEmailPage() {
  const [state, setState] = useState<VerificationState>("checking");
  const [message, setMessage] = useState("Preparing your verification…");

  useEffect(() => {
    let active = true;

    async function verify() {
      const fragment = window.location.hash.startsWith("#")
        ? window.location.hash.slice(1)
        : "";
      const params = new URLSearchParams(fragment);
      const token = params.get("token") || "";

      // Remove the bearer token from the visible URL before making any request.
      window.history.replaceState(null, "", window.location.pathname + window.location.search);

      if (token.length < 32 || token.length > 512) {
        if (active) {
          setState("invalid");
          setMessage("This verification link is missing or invalid. Request a new email to continue.");
        }
        return;
      }

      try {
        const response = await fetch("/api/v1/auth/verify-email", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
          cache: "no-store",
        });
        const data = await response.json().catch(() => ({}));
        if (!active) return;
        if (response.ok) {
          setState("success");
          setMessage(typeof data.message === "string" ? data.message : "Your email has been verified. You can now sign in.");
        } else if (response.status === 400) {
          setState("invalid");
          setMessage("This verification link is invalid, expired, or has already been used. Request a new verification email.");
        } else {
          setState("unavailable");
          setMessage("Email verification is temporarily unavailable. Please try again shortly.");
        }
      } catch {
        if (active) {
          setState("unavailable");
          setMessage("We could not reach the account service. Please try again shortly.");
        }
      }
    }

    void verify();
    return () => { active = false; };
  }, []);

  return <>
    <SiteHeader/>
    <main className="wrap">
      <section className="form-card" aria-labelledby="verification-title">
        <p className="eyebrow">Email verification</p>
        <h1 id="verification-title">{state === "success" ? "Email verified" : state === "checking" ? "Verifying your email" : "Verification link issue"}</h1>
        <p className="notice" role="status" aria-live="polite">{message}</p>
        {state === "success" ? <Link className="button" href="/login">Continue to sign in</Link> : state !== "checking" ? <p className="fine"><Link href="/resend-verification">Request a new verification email</Link></p> : null}
      </section>
    </main>
    <SiteFooter/>
  </>;
}
