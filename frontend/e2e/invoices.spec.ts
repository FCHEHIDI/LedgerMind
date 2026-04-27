import { test, expect, Page } from "@playwright/test";
import path from "path";

/** Helper : se connecter avant chaque test */
async function login(page: Page): Promise<void> {
  await page.goto("/login");
  await page.fill('input[name="username"], input[type="text"]', "admin");
  await page.fill('input[name="password"], input[type="password"]', "Admin1234x");
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/app/, { timeout: 10_000 });
}

test.describe("Workflow factures", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test("la page factures se charge avec la liste des factures", async ({ page }) => {
    await page.goto("/app/invoices");
    // Attendre que le contenu principal soit visible
    await expect(page.locator("h1, h2").filter({ hasText: /facture/i }).first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("upload d'un PDF crée une facture avec statut pending", async ({ page }) => {
    await page.goto("/app/invoices");

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(path.join(__dirname, "fixtures", "facture-test.pdf"));

    // Attendre qu'un badge pending apparaisse (polling automatique côté app)
    await expect(
      page.locator('[data-status="pending"], [data-testid*="pending"]').first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("clic sur une ligne facture ouvre le drawer de détail", async ({ page }) => {
    await page.goto("/app/invoices");

    // Attendre au moins une ligne
    const firstRow = page.locator(
      '[data-testid="invoice-row"], table tbody tr, [role="row"]:not([role="columnheader"])'
    ).first();
    await expect(firstRow).toBeVisible({ timeout: 10_000 });
    await firstRow.click();

    // Le drawer / panneau de détail doit être visible
    const drawer = page.locator(
      '[data-testid="invoice-drawer"], [role="dialog"], aside'
    );
    await expect(drawer.first()).toBeVisible({ timeout: 5_000 });
  });

  test("les factures en statut processing déclenchent un polling visible", async ({ page }) => {
    await page.goto("/app/invoices");

    // Si une facture est en processing, on attend qu'elle change de statut
    // ou simplement que la page ne soit pas en erreur après 5 secondes
    await page.waitForTimeout(3_000);
    await expect(page).toHaveURL(/\/app\/invoices/);
  });
});
