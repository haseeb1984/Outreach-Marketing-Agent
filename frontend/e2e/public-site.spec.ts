import { expect, test } from "@playwright/test";

const publicRoutes = [
  ["/", "Your smart outreach partner"],
  ["/features", "Platform capabilities"],
  ["/faq", "Frequently asked questions"],
  ["/login", "Sign in to your workspace"],
  ["/register", "Start with your workspace"],
  ["/privacy", "Privacy Policy"],
  ["/terms", "Terms of Use"],
  ["/contact", "Contact support"],
  ["/pricing", "Transparent plans. Server-verified access."],
  ["/how-it-works", "How it works"],
] as const;

test.describe("public website browser acceptance", () => {
  for (const [route, expectedContent] of publicRoutes) {
    test(`${route} renders successfully in a real browser`, async ({ page }) => {
      const pageErrors: string[] = [];
      page.on("pageerror", (error) => pageErrors.push(error.message));
      const response = await page.goto(route);
      expect(response?.status(), `${route} HTTP response`).toBe(200);
      await expect(page.locator("body")).toContainText(expectedContent);
      await expect(page.locator("body")).not.toContainText("Application error: a server-side exception has occurred");
      expect(pageErrors, `${route} browser runtime errors`).toEqual([]);
      await page.screenshot({
        path: `artifacts/screenshots/public-${route === "/" ? "home" : route.slice(1)}-desktop.png`,
        fullPage: true,
        animations: "disabled",
      });
    });
  }

  test("public pages expose core document and landmark semantics", async ({ page }) => {
    for (const [route] of publicRoutes) {
      await page.goto(route);
      await expect(page.locator("html")).toHaveAttribute("lang", /.+/);
      await expect(page.getByRole("main"), `${route} main landmark`).toHaveCount(1);
      await expect(page.getByRole("heading", { level: 1 }), `${route} primary heading`).toHaveCount(1);
      const unnamedControls = await page.locator('button, a, input:not([type="hidden"]), textarea, select').evaluateAll((elements) =>
        elements.filter((element) => {
          const explicit = element.getAttribute("aria-label") || element.getAttribute("aria-labelledby");
          const text = (element.textContent || "").trim();
          if (explicit || text) return false;
          if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement) {
            return element.labels?.length === 0;
          }
          return !(element instanceof HTMLAnchorElement && element.querySelector("img[alt]"));
        }).length
      );
      expect(unnamedControls, `${route} interactive controls need accessible names`).toBe(0);
      const brokenLabelReferences = await page.locator("[aria-labelledby]").evaluateAll((elements) => {
        const ids = new Set(Array.from(document.querySelectorAll("[id]")).map((element) => element.id));
        return elements.filter((element) =>
          (element.getAttribute("aria-labelledby") || "").trim().split(/\s+/).filter(Boolean).some((id) => !ids.has(id))
        ).length;
      });
      expect(brokenLabelReferences, `${route} aria-labelledby references must resolve to existing elements`).toBe(0);
      const duplicateIds = await page.locator("[id]").evaluateAll((elements) => {
        const counts = new Map<string, number>();
        for (const element of elements) {
          const id = element.id;
          counts.set(id, (counts.get(id) || 0) + 1);
        }
        return Array.from(counts.values()).filter((count) => count > 1).length;
      });
      expect(duplicateIds, `${route} element IDs must be unique`).toBe(0);
      const unnamedImages = await page.locator("img:not([aria-hidden='true'])").evaluateAll((images) =>
        images.filter((image) => !image.hasAttribute("alt")).length
      );
      expect(unnamedImages, `${route} informative images need alt text`).toBe(0);
    }
  });

  test("homepage remains usable at mobile viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await expect(page.locator("body")).toContainText("Your smart outreach partner");
    const dimensions = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      content: document.documentElement.scrollWidth,
    }));
    expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport + 1);
    await page.screenshot({
      path: "artifacts/screenshots/public-home-mobile.png",
      fullPage: true,
      animations: "disabled",
    });
  });
});
