import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

/**
 * Automated accessibility audit (axe-core, WCAG 2 A and AA) of every page, signed in as an admin of an
 * accounts-mode server. A page may not have a single violation. Automated rules cover roughly a third of
 * WCAG; this catches the mechanical failures (labels, names, contrast, landmarks, focus order of
 * headings, duplicate ids), not whether a screen reader user can finish a task.
 */
const TOKEN = process.env.E2E_ACCOUNTS_TOKEN;
const API = process.env.E2E_API_URL ?? "http://localhost:8000";
test.skip(!TOKEN, "needs E2E_ACCOUNTS_TOKEN (an accounts-mode API)");

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

async function audit(page: Page, url: string, label: string) {
  await page.goto(url);
  await page.waitForLoadState("networkidle");
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  const summary = result.violations.map((v) => `${v.id} (${v.impact}) x${v.nodes.length}: ${v.nodes[0]?.target.join(" ")}`);
  console.log(`a11y ${label}: ${result.violations.length} violation type(s)${summary.length ? "\n  " + summary.join("\n  ") : ""}`);
  return result.violations;
}

function syntheticDrhp(): string {
  const dir = mkdtempSync(path.join(tmpdir(), "a11y-"));
  const out = path.join(dir, "a11y-drhp.pdf");
  const root = path.resolve(__dirname, "../../..");
  execFileSync(
    path.resolve(root, ".venv/bin/python"),
    ["-c", `from tests.screening.fixtures.pdf_factory import standard_drhp; open(${JSON.stringify(out)}, 'wb').write(standard_drhp())`],
    { cwd: root },
  );
  return out;
}

for (const scheme of ["light", "dark"] as const) {
test(`signed-in pages have no automatically detectable accessibility violations (${scheme} theme)`, async ({ page, request }) => {
  await page.emulateMedia({ colorScheme: scheme });
  const h = { Authorization: `Bearer ${TOKEN}` };
  const made = await request.post(`${API}/api/v1/cases`, { headers: h, data: { company_name: `A11y Co ${Date.now()}` } });
  const caseId = (await made.json()).id as string;
  await request.post(`${API}/api/v1/cases/${caseId}/documents`, {
    headers: h,
    multipart: { file: { name: "d.pdf", mimeType: "application/pdf", buffer: Buffer.from(await (await import("node:fs/promises")).readFile(syntheticDrhp())) } },
  });
  const rep = await request.post(`${API}/api/v1/cases/${caseId}/screenings`, { headers: h });
  const reportId = (await rep.json()).report_id as string;
  await request.post(`${API}/api/v1/cases/${caseId}/comments`, { headers: h, data: { body: "A note for the audit" } });

  await page.addInitScript((t) => window.sessionStorage.setItem("ipo-dd.api-key", t as string), TOKEN);
  const pages: [string, string][] = [
    ["/", "dashboard"],
    ["/cases", "cases"],
    ["/cases/new", "new case"],
    [`/cases/${caseId}`, "case"],
    [`/cases/${caseId}?tab=documents`, "case documents"],
    ["/reports", "reports"],
    [`/reports/${reportId}`, "report"],
    ["/review", "review"],
    ["/rules", "rules"],
    ["/settings", "settings"],
    ["/team", "team"],
    ["/account", "account"],
    ["/organisation", "organisation"],
    ["/notifications", "notifications"],
  ];
  const failures: string[] = [];
  for (const [url, label] of pages) {
    const violations = await audit(page, url, `${label} [${scheme}]`);
    for (const v of violations) failures.push(`${label}: ${v.id} (${v.impact}) ${v.help}`);
  }
  expect(failures, failures.join("\n")).toEqual([]);
});
}

test("the sign-in and invitation pages have no automatically detectable violations", async ({ page }) => {
  const failures: string[] = [];
  for (const [url, label] of [
    ["/login", "login"],
    ["/login?error=Something%20went%20wrong", "login with an error"],
    ["/invite?token=not-a-real-token-0123456789", "invite"],
  ] as const) {
    for (const v of await audit(page, url, label)) failures.push(`${label}: ${v.id} (${v.impact}) ${v.help}`);
  }
  expect(failures, failures.join("\n")).toEqual([]);
});
