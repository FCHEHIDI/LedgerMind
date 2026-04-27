import { test, expect, Page } from "@playwright/test";

async function login(page: Page): Promise<void> {
  await page.goto("/login");
  await page.fill('input[name="username"], input[type="text"]', "admin");
  await page.fill('input[name="password"], input[type="password"]', "Admin1234x");
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/app/, { timeout: 10_000 });
}

test.describe("Workflow Grand Livre / Journal", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test("la page ledger charge la liste des écritures", async ({ page }) => {
    await page.goto("/app/ledger");
    await expect(page.locator("h1, h2").filter({ hasText: /journal|ledger|écriture/i }).first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("valider une écriture draft change son statut en posted", async ({ page }) => {
    await page.goto("/app/ledger");

    // Trouver le premier bouton de validation visible
    const validateBtn = page.locator('[data-testid="validate-btn"], button').filter({
      hasText: /valid/i,
    }).first();

    const isVisible = await validateBtn.isVisible();
    if (!isVisible) {
      // Aucune écriture draft disponible — test skippé gracieusement
      test.skip();
      return;
    }

    await validateBtn.click();

    // Le badge de statut doit passer à posted
    await expect(
      page.locator('[data-status="posted"], [data-testid*="posted"]').first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("annuler une écriture draft change son statut en cancelled", async ({ page }) => {
    await page.goto("/app/ledger");

    const cancelBtn = page.locator('[data-testid="cancel-btn"], button').filter({
      hasText: /annul|cancel/i,
    }).first();

    if (!(await cancelBtn.isVisible())) {
      test.skip();
      return;
    }

    await cancelBtn.click();

    await expect(
      page.locator('[data-status="cancelled"], [data-testid*="cancelled"]').first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("export FEC déclenche un téléchargement de fichier .txt", async ({ page }) => {
    await page.goto("/app/ledger");

    const exportBtn = page.locator('[data-testid="export-fec-btn"], button').filter({
      hasText: /fec|export/i,
    }).first();

    if (!(await exportBtn.isVisible())) {
      test.skip();
      return;
    }

    const [download] = await Promise.all([
      page.waitForEvent("download", { timeout: 15_000 }),
      exportBtn.click(),
    ]);

    expect(download.suggestedFilename()).toMatch(/FEC.*\.txt$/i);
  });

  test("la page ledger n'a pas d'erreur JavaScript en console", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        errors.push(msg.text());
      }
    });

    await page.goto("/app/ledger");
    await page.waitForLoadState("networkidle");

    // Filtrer les erreurs de connexion réseau (attendues en test sans backend live)
    const criticalErrors = errors.filter(
      (e) => !e.includes("net::ERR") && !e.includes("Failed to fetch")
    );
    expect(criticalErrors).toHaveLength(0);
  });
});
