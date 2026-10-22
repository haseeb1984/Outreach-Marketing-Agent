import type { Metadata } from "next";
import InvitationAcceptance from "./InvitationAcceptance";

export const metadata: Metadata = {
  title: "Accept workspace invitation",
  description: "Accept an invitation to join a workspace.",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function AcceptInvitationPage() {
  return <InvitationAcceptance />;
}
