import { expect, test } from "@playwright/test";

test.describe("account and authenticated browser journeys", () => {
  test("registration submits same-origin credentials and shows the neutral confirmation", async ({ page }) => {
    let requestBody: Record<string, unknown> | undefined;
    await page.route("**/api/v1/auth/register", async (route) => {
      requestBody = route.request().postDataJSON();
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({ message: "If registration can proceed, a verification email will be sent." }),
      });
    });

    await page.goto("/register");
    await page.getByLabel("Work email").fill("browser-test@example.test");
    await page.getByLabel("Password").fill("Correct-Horse-Battery-42!");
    await page.getByRole("button", { name: "Create account" }).click();

    await expect(page.getByRole("status")).toContainText("If registration can proceed");
    expect(requestBody).toEqual({
      email: "browser-test@example.test",
      password: "Correct-Horse-Battery-42!",
    });
  });

  test("login rejects invalid credentials without exposing backend details", async ({ page }) => {
    await page.route("**/api/v1/auth/login", async (route) => {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "email_or_password_incorrect" }),
      });
    });

    await page.goto("/login");
    await page.getByLabel("Email address").fill("browser-test@example.test");
    await page.getByLabel("Password").fill("incorrect-password");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByRole("alert")).toHaveText("Email or password was not accepted.");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("password recovery shows the same confirmation for an eligible account", async ({ page }) => {
    await page.route("**/api/v1/auth/password-reset/request", async (route) => {
      expect(route.request().method()).toBe("POST");
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({ message: "If the account is eligible, a password-reset email will be sent." }),
      });
    });

    await page.goto("/forgot-password");
    await page.getByLabel("Email address").fill("browser-test@example.test");
    await page.getByRole("button", { name: "Send reset link" }).click();
    await expect(page.getByRole("status")).toContainText("If the account is eligible");
  });

  test("verification token is removed from the visible URL before it is posted", async ({ page }) => {
    let postedToken = "";
    await page.route("**/api/v1/auth/verify-email", async (route) => {
      postedToken = String(route.request().postDataJSON().token || "");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ message: "Your email has been verified. You can now sign in." }),
      });
    });

    await page.goto("/verify-email#token=browser-verification-token-0123456789abcdef");
    await expect(page.getByRole("heading", { name: "Email verified" })).toBeVisible();
    await expect.poll(() => page.url()).toMatch(/\/verify-email$/);
    expect(postedToken).toBe("browser-verification-token-0123456789abcdef");
  });

  test("expired authenticated session returns the user to sign in", async ({ page }) => {
    await page.route("**/api/v1/auth/me", async (route) => {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "authentication_required" }),
      });
    });

    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login$/);
  });
});
