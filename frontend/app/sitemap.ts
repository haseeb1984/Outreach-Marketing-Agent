import type { MetadataRoute } from "next";

const publicPaths = ["/", "/product", "/pricing", "/faq", "/privacy", "/terms"] as const;

export default function sitemap(): MetadataRoute.Sitemap {
  const configured = process.env.NEXT_PUBLIC_SITE_URL || process.env.SITE_URL;
  if (!configured) return [];
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
    priority: path === "/" ? 1 : path === "/product" || path === "/pricing" ? 0.8 : 0.5,
  }));
}
