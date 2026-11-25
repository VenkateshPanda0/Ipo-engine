import { expect, test } from "@playwright/test";

/**
 * Accounts mode, end to end in a real browser. Needs an API started with ACCOUNTS_ENABLED=true and a
 * personal token for an admin (E2E_ACCOUNTS_TOKEN); skipped otherwise. Sign-in with Google is covered
 * by the API tests against a fake identity provider; here the browser signs in with the token.
 */
const TOKEN = process.env.E2E_ACCOUNTS_TOKEN;
test.skip(!TOKEN, "needs E2E_ACCOUNTS_TOKEN (an accounts-mode API)");

test("sign in with a token, then use the team features", async ({ page }) => {
  // Not signed in: the shell sends you to the login page and back afterwards.
  await page.goto("/team");
  await expect(page).toHaveURL(/\/login\?next=%2Fteam/);
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByRole("textbox", { name: "API token" }).fill("ipo_not_a_real_token");
  await page.getByRole("button", { name: /use for this tab/i }).click();
  await expect(page.getByText("That token was not accepted.")).toBeVisible();
  await page.getByRole("textbox", { name: "API token" }).fill(TOKEN!);
  await page.getByRole("button", { name: /use for this tab/i }).click();
  await expect(page).toHaveURL(/\/team$/);
  await expect(page.getByRole("heading", { name: "Team" })).toBeVisible();

  // Invite someone: the link is shown once and the invitation is listed.
  const who = `new${Date.now()}@example.com`;
  await page.getByLabel("Email address").fill(who);
  await page.getByRole("button", { name: /create invitation/i }).click();
  await expect(page.getByText(/shown only now/i)).toBeVisible();
  await expect(page.getByText(/\/invite\?token=/)).toBeVisible();
  await expect(page.getByRole("cell", { name: who })).toBeVisible();

  // A case, a comment, an assignment.
  const company = `Team Case ${Date.now()}`;
  await page.goto("/cases/new");
  await page.getByLabel(/company name/i).fill(company);
  await page.getByRole("button", { name: /create case/i }).click();
  await expect(page).toHaveURL(/\/cases\/[0-9a-f-]+/);
  await expect(page.getByRole("heading", { name: "Team and discussion" })).toBeVisible();
  await page.getByLabel("Add a comment").fill("Please check the promoter holding.");
  await page.getByRole("button", { name: "Comment" }).click();
  await expect(page.getByText("Please check the promoter holding.")).toBeVisible();
  const assignee = page.getByLabel("Assignee");
  await assignee.selectOption({ index: 1 });
  await expect(assignee).not.toHaveValue("");

  // The case list: assigned to me, and a spreadsheet download.
  await page.goto("/cases");
  await page.getByLabel("Assigned to me").check();
  await expect(page.getByRole("link", { name: company })).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "CSV" }).click();
  expect((await download).suggestedFilename()).toBe("cases.csv");

  // My account: a new token is shown once.
  await page.goto("/account");
  await page.getByLabel("Token name").fill("e2e");
  await page.getByRole("button", { name: /create token/i }).click();
  await expect(page.getByText(/cannot be shown again/i)).toBeVisible();
  await expect(page.locator("code", { hasText: /^ipo_[\w-]{30,}$/ })).toBeVisible();

  // Organisation: settings and the data controls exist for an admin.
  await page.goto("/organisation");
  const fourEyes = page.getByRole("checkbox", { name: /four eyes/i });
  const before = await fourEyes.isChecked();
  await fourEyes.click();
  await expect(fourEyes).toBeChecked({ checked: !before });
  await page.reload();
  await expect(page.getByRole("checkbox", { name: /four eyes/i })).toBeChecked({ checked: !before }); // saved
  await page.getByRole("checkbox", { name: /four eyes/i }).click(); // put it back
  await expect(page.getByRole("button", { name: /export data/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /delete organisation/i })).toBeDisabled();

  // Notifications page loads.
  await page.goto("/notifications");
  await expect(page.getByRole("heading", { name: "Notifications" })).toBeVisible();
});
