import { test, expect } from "@playwright/test";

test.skip(!process.env.GARD_E2E_TOKEN, "Set GARD_E2E_TOKEN to run lab E2E smoke");

test("sign-in and dashboard", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByLabel(/jwt bearer token/i).fill(process.env.GARD_E2E_TOKEN!);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
});
