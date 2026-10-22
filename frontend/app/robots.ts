import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  const configured = process.env.NEXT_PUBLIC_SITE_URL || process.env.SITE_URL;
  let sitemap: string | undefined;
  if (configured) {
    try {
      const base = new URL(configured);
      if (base.protocol === "https:" && !base.username && !base.password && !base.search && !base.hash) {
        sitemap = base.toString().replace(/\/$/, "") + "/sitemap.xml";
      }
    } catch {
      // An invalid site URL must not produce a malformed Sitemap directive.
    }
  }
  return {
    rules: [
      { userAgent: "*", allow: "/", disallow: ["/api/", "/dashboard", "/login", "/register", "/verify-email", "/reset-password", "/invitations/"] },
    ],
    ...(sitemap ? { sitemap } : {}),
  };
}
