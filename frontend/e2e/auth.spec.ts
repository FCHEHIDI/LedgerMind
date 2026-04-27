import { test, expect } from "@playwright/test";

test.describe("Authentification", () => {
  test("login avec credentials valides redirige vers /app", async ({ page }) => {
    await page.goto("/login");

    await page.fill('input[name="username"], input[type="text"]', "admin");
    await page.fill('input[name="password"], input[type="password"]', "Admin1234x");
    await page.click('button[type="submit"]');

    await expect(page).toHaveURL(/\/app/, { timeout: 10_000 });
  });

  test("login avec mauvais mot de passe affiche une erreur", async ({ page }) => {
    await page.goto("/login");

    await page.fill('input[name="username"], input[type="text"]', "admin");
    await page.fill('input[name="password"], input[type="password"]', "wrong-password");
    await page.click('button[type="submit"]');

    // L'URL reste sur /login et un message d'erreur apparaît
    await expect(page).toHaveURL(/\/login/, { timeout: 5_000 });
    const errorBanner = page.locator('[data-testid="error-banner"], [role="alert"]');
    await expect(errorBanner).toBeVisible({ timeout: 5_000 });
  });

  test("accès direct à /app/dashboard sans token redirige vers /login", async ({ page }) => {
    // Naviguer sans aucun token stocké (contexte vierge)
    await page.goto("/app/dashboard");
    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
  });

  test("accès direct à /app/invoices sans token redirige vers /login", async ({ page }) => {
    await page.goto("/app/invoices");
    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
  });
});
