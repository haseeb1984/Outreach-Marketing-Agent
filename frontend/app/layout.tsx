import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  metadataBase: new URL("https://outreach.juncsys.com"),
  title: { default: "Outreach Marketing Agent | Evidence-led growth", template: "%s | Outreach Marketing Agent" },
  description: "Research public-web prospects, prepare reviewed outreach and assess verified website signals in one accountable workspace.",
  applicationName: "Outreach Marketing Agent",
  icons: { icon: "/icon.svg", shortcut: "/icon.svg" },
  openGraph: { type: "website", siteName: "Outreach Marketing Agent", title: "Outreach Marketing Agent", description: "Public-web prospect research, reviewed outreach and practical website insights.", url: "https://outreach.juncsys.com" },
  robots: { index: true, follow: true },
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
