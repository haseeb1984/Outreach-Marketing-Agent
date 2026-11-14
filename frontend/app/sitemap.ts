import type { MetadataRoute } from "next";

const publicPaths = [
  "/", "/product", "/features", "/how-it-works", "/pricing", "/about",
  "/faq",
] as const;

export default function sitemap(): MetadataRoute.Sitemap {
  const configured = process.env.NEXT_PUBLIC_SITE_URL || process.env.SITE_URL || "https://outreach.juncsys.com";
  let base: URL;
  try {
    base = new URL(configured);
    if (base.protocol !== "https:" || base.username || base.password || base.search || base.hash) return [];
  } catch {
    return [];
  }
  const origin = base.toString().replace(/\/$/, "");
  return publicPaths.map((path) => ({
    url: origin + path,
    changeFrequency: path === "/" ? "weekly" : "monthly",
    priority: path === "/" ? 1 : ["/product", "/features", "/pricing", "/how-it-works"].includes(path) ? 0.8 : 0.5,
  }));
}
