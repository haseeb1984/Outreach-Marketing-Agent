import type { Metadata } from "next";
import { SiteHeader, SiteFooter } from "../components/site-chrome";
import PricingPlanCatalog from "./plan-catalog";

export const metadata: Metadata = {
  title: "Plans and pricing",
  description: "Explore server-configured Outreach Marketing Agent workspace plans and verified billing availability.",
};

export default function PricingPage() {
  return <><SiteHeader/><main className="wrap"><PricingPlanCatalog/></main><SiteFooter/></>;
}
