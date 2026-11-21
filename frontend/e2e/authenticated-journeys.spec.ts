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

  test("verified account login loads a workspace and sends CSRF on a protected mutation", async ({ page }) => {
    const csrfToken = "browser-csrf-token-0123456789abcdef";
    let mutationHeaders: Record<string, string> | undefined;

    await page.route("**/api/v1/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.pathname === "/api/v1/auth/login") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ user: { user_id: "user-1", email: "verified@example.test" }, csrf_token: csrfToken }),
        });
      } else if (url.pathname === "/api/v1/auth/me") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ user: { user_id: "user-1", email: "verified@example.test" }, csrf_token: csrfToken }),
        });
      } else if (url.pathname === "/api/v1/workspaces" && request.method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ items: [{ id: "workspace-1", name: "Acceptance workspace", role: "owner" }] }),
        });
      } else if (url.pathname === "/api/v1/workspaces" && request.method() === "POST") {
        mutationHeaders = request.headers();
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify({ workspace_id: "workspace-2", name: "Second workspace", role: "owner" }),
        });
      } else if (url.pathname === "/api/v1/auth/sessions") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ items: [{ id: "session-current", created_at: "2026-01-01T00:00:00Z", last_seen_at: "2026-01-01T00:00:00Z", expires_at: "2027-01-01T00:00:00Z", is_current: true }] }),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ items: [] }),
        });
      }
    });

    await page.goto("/login");
    await page.getByLabel("Email address").fill("verified@example.test");
    await page.getByLabel("Password").fill("correct-password");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByLabel("Active workspace")).toHaveValue("workspace-1");
    await expect(page.getByText("verified@example.test")).toBeVisible();

    await page.getByLabel("Create another workspace").fill("Second workspace");
    await page.getByRole("button", { name: "Create workspace" }).click();

    await expect(page.getByLabel("Active workspace")).toHaveValue("workspace-2");
    expect(mutationHeaders?.["x-csrf-token"]).toBe(csrfToken);
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

    await expect(page.locator("p.notice[role='alert']")).toHaveText("Email or password was not accepted.");
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

  test("influencer discovery submits selected platforms and displays review-only candidates", async ({ page }) => {
    const csrfToken = "influencer-csrf-token-0123456789abcdef";
    let submitted: Record<string, unknown> | undefined;
    let searchCsrf = "";

    await page.route("**/api/v1/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.pathname === "/api/v1/auth/login" || url.pathname === "/api/v1/auth/me") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ user: { user_id: "user-1", email: "verified@example.test" }, csrf_token: csrfToken }),
        });
      } else if (url.pathname === "/api/v1/workspaces" && request.method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ items: [{ id: "workspace-1", name: "Acceptance workspace", role: "owner" }] }),
        });
      } else if (url.pathname === "/api/v1/research/influencers/search") {
        submitted = request.postDataJSON();
        searchCsrf = request.headers()["x-csrf-token"] || "";
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            items: [{
              profile_url: "https://instagram.com/karachi.food.creator",
              platform: "instagram",
              title: "Karachi Food Creator",
              description: "Independent restaurant reviews in Karachi.",
              relevance_score: 82,
              relevance_reasons: ["karachi", "food", "creator"],
              requires_human_review: true,
              audience_metrics: null,
              audience_metrics_status: "not_available_from_search_results",
            }],
            notice: "Review creator identity and audience data independently.",
          }),
        });
      } else if (url.pathname === "/api/v1/auth/sessions") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ items: [] }),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ items: [] }),
        });
      }
    });

    await page.goto("/login");
    await page.getByLabel("Email address").fill("verified@example.test");
    await page.getByLabel("Password").fill("correct-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/dashboard$/);

    await page.getByLabel("Creator niche, audience and market").fill("Karachi food creators");
    await page.getByLabel("Platforms (choose one or more)").selectOption(["instagram", "youtube"]);
    await page.getByRole("button", { name: "Discover creators" }).click();

    await expect(page.getByRole("heading", { name: "Karachi Food Creator" })).toBeVisible();
    await expect(page.getByText(/Audience metrics unavailable/)).toBeVisible();
    expect(submitted).toMatchObject({
      workspace_id: "workspace-1",
      query: "Karachi food creators",
      platforms: ["instagram", "youtube"],
      count: 10,
    });
    expect(typeof submitted?.idempotency_key).toBe("string");
    expect(searchCsrf).toBe(csrfToken);
  });

});
