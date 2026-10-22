import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: { default: "Outreach Marketing Agent", template: "%s | Outreach Marketing Agent" },
  description: "Evidence-led prospect discovery, business-specific outreach, competitor intelligence and website growth.",
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
