import type { Metadata } from "next";
import InvitationAcceptance from "./InvitationAcceptance";

export const metadata: Metadata = {
  title: "Accept workspace invitation",
  description: "Accept an invitation to join a workspace.",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default async function AcceptInvitationPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string | string[] }>;
}) {
  const params = await searchParams;
  const token = typeof params.token === "string" ? params.token : "";
  return <InvitationAcceptance token={token} />;
}
