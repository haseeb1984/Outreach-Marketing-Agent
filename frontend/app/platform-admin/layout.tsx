import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Platform Administration | Outreach Marketing Agent",
  robots: { index: false, follow: false, noarchive: true },
};

export default function PlatformAdminLayout({ children }: { children: React.ReactNode }) {
  return children;
}
