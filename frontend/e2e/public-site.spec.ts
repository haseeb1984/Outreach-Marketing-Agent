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
    });
  }

  test("homepage remains usable at mobile viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await expect(page.locator("body")).toContainText("Your smart outreach partner");
    const dimensions = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      content: document.documentElement.scrollWidth,
    }));
    expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport + 1);
  });
});
