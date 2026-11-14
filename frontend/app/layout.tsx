import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  metadataBase: new URL("https://outreach.juncsys.com"),
  title: { default: "Outreach Marketing Agent | Evidence-led growth", template: "%s | Outreach Marketing Agent" },
  description: "Discover relevant prospects, prepare thoughtful outreach and understand competitors with evidence-led growth workflows.",
  applicationName: "Outreach Marketing Agent",
  icons: { icon: "/icon.svg", shortcut: "/icon.svg" },
  openGraph: { type: "website", siteName: "Outreach Marketing Agent", title: "Outreach Marketing Agent", description: "Evidence-led prospect research, responsible outreach and practical growth insights.", url: "https://outreach.juncsys.com" },
  robots: { index: true, follow: true },
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
