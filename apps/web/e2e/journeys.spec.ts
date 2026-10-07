import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

const FOCUS_QUESTION = "Which improvement should we investigate first?";
const WHOSE_QUESTION = "Whose coordination should the interviews focus on first?";

async function expectAccessible(page: Page, surface: string) {
  // Measure resting colors: no hover, and no transition (such as a button fading in once enabled) mid-flight.
  await page.mouse.move(0, 0);
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== "running"));
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const found = results.violations.flatMap((v) =>
    v.nodes.map((n) => `${surface}: ${v.id} at ${n.target.join(" ")}: ${n.failureSummary ?? ""}`),
  );
  expect(found).toEqual([]);
}

async function newBrief(page: Page, fixtureLabel: string) {
  await page.goto("/");
  await expect(page.getByText("Fixture mode: canned responses, not a live model")).toBeVisible();
  const newButton = page.getByRole("button", { name: "New brief" });
  if (await newButton.isVisible()) await newButton.click();
  await page.getByRole("button", { name: fixtureLabel }).click();
  await page.getByRole("button", { name: "Read brief" }).click();
  await expect(page.getByRole("heading", { name: "Current understanding" })).toBeVisible();
}

const decision = (page: Page) => page.locator("#decision");
const row = (page: Page, label: string) => page.locator("[data-section]", { hasText: label });

async function expectFocusOnDecisionHeading(page: Page, name: string) {
  await expect(decision(page).getByRole("heading", { name, level: 2 })).toBeFocused();
}

test("clear brief: no questions, existing direction carries through to a reviewed export", async ({ page }) => {
  await newBrief(page, "Clear brief (journey 1)");
  await expect(page.getByRole("heading", { name: "Nothing needs your answer now" })).toBeFocused();
  await expect(page.getByText("No open questions.")).toBeVisible();
  await expect(row(page, "Next step")).toContainText("Prepare a design brief, not an implementation.");
  await expect(page.getByText("A consolidated guide saves engineers time.")).toBeVisible();
  await expectAccessible(page, "working brief");

  await page.getByRole("button", { name: "Review the handoff" }).click();
  await expect(page.getByText("Revision 1 is a draft.")).toBeVisible();
  await expect(page.getByTestId("handoff")).toContainText("DRAFT. Revision 1 has not been reviewed.");
  await expectAccessible(page, "review");
  await page.getByRole("button", { name: "Mark revision 1 reviewed" }).click();
  await expect(page.getByText("Revision 1 is reviewed.").first()).toBeVisible();
  await expect(page.getByTestId("handoff")).toContainText("Reviewed. Revision 1");
});

test("ambiguous brief: one focused question, a choice, a follow-up, and a deferral", async ({ page }) => {
  await newBrief(page, "Ambiguous brief (journey 2)");
  await expect(decision(page).getByRole("heading", { name: FOCUS_QUESTION })).toBeVisible();
  for (const radio of await decision(page).getByRole("radio").all()) await expect(radio).not.toBeChecked();
  await expect(row(page, "Audience and circumstances")).toContainText("Not established");

  // Keyboard: arrow keys move the choice within the radio group; every option has an accessible name.
  const coordination = decision(page).getByRole("radio", { name: /Coordination during service/ });
  await coordination.focus();
  await page.keyboard.press("Space");
  await expect(coordination).toBeChecked();
  // Radix selects on arrow-key focus while the key is held, as a person's key press is.
  await page.keyboard.press("ArrowDown", { delay: 50 });
  await expect(decision(page).getByRole("radio", { name: /Owner visibility afterwards/ })).toBeChecked();
  await page.keyboard.press("ArrowUp", { delay: 50 });
  await expect(coordination).toBeChecked();
  await decision(page).getByLabel("Reason (optional)").fill("Service is where it hurts.");
  await decision(page).getByRole("button", { name: "Record choice" }).click();

  await expect(page.getByRole("status")).toContainText(`New question: ${WHOSE_QUESTION}`);
  await expectFocusOnDecisionHeading(page, WHOSE_QUESTION);
  await expect(row(page, "Direction to pursue")).toContainText(
    "Investigate how incidents are coordinated during service.",
  );
  await expect(row(page, "Direction to pursue")).toContainText("Selected by you from proposed options");

  await decision(page).getByRole("button", { name: "Leave this open" }).click();
  await expect(page.getByRole("heading", { name: "Nothing needs your answer now" })).toBeFocused();
  await expect(row(page, "Audience and circumstances")).toContainText("Not established");
  await expect(page.getByText("Left open by you")).toBeVisible();
  await expectAccessible(page, "working brief after deferral");
});

test("correction: change a selected answer, withdraw it, and answer in your own words", async ({ page }) => {
  await newBrief(page, "Ambiguous brief (journey 2)");
  await decision(page)
    .getByRole("radio", { name: /Owner visibility afterwards/ })
    .check();
  await decision(page).getByRole("button", { name: "Record choice" }).click();
  await expect(row(page, "Direction to pursue")).toContainText("owners understand incidents");

  await page.getByText("Answered questions (1)").click();
  await page.getByRole("button", { name: "Change answer" }).click();
  await expectFocusOnDecisionHeading(page, FOCUS_QUESTION);
  await expect(decision(page).getByText("Change your answer")).toBeVisible();
  await expect(
    decision(page).getByRole("radio", { name: /Owner visibility afterwards \(current answer\)/ }),
  ).toBeDisabled();

  await decision(page).getByRole("button", { name: "Withdraw answer and leave open" }).click();
  await expect(row(page, "Direction to pursue")).toContainText("Not established");
  await expect(page.getByTestId("history")).toContainText("The earlier answer no longer applies.");
  await expect(page.getByTestId("history").getByText(/Superseded by d\d+/)).toHaveCount(1);

  await page.getByRole("button", { name: "Answer this now" }).first().click();
  await expectFocusOnDecisionHeading(page, FOCUS_QUESTION);
  await decision(page)
    .getByRole("radio", { name: /Something else/ })
    .check();
  await decision(page).getByRole("button", { name: "Short reply" }).click();
  await decision(page).getByRole("button", { name: "Send answer" }).click();
  await expect(row(page, "Direction to pursue")).toContainText("Investigate coordination first.");
  await expect(row(page, "Direction to pursue")).toContainText("From your reply");
  await expect(page.getByTestId("history").getByText(/Superseded by d\d+/)).toHaveCount(2);
});

test("review and export come from one revision, survive reload, and a correction makes a draft", async ({
  page,
  request,
}) => {
  await newBrief(page, "Ambiguous brief (journey 2)");
  await decision(page).getByRole("button", { name: "Leave this open" }).click();
  await page.getByRole("link", { name: "Review and export" }).click();
  await expect(page.getByText(/2 questions remain open/)).toBeVisible();
  const reviewButton = page.getByRole("button", { name: /Mark revision \d+ reviewed/ });
  const revision = Number((await reviewButton.textContent())?.match(/\d+/)?.[0]);
  await reviewButton.click();
  await expect(page.getByTestId("handoff")).toContainText(`Reviewed. Revision ${revision}`);

  const current = await (await request.get("/api/projects/current")).json();
  const id = current.project.id as string;
  const json = await (await request.get(`/api/projects/${id}/exports/json`)).json();
  const markdown = await (await request.get(`/api/projects/${id}/exports/markdown`)).text();
  expect([json.status, json.revision]).toEqual(["reviewed", revision]);
  expect(markdown).toContain(`Reviewed. Revision ${revision}`);

  await page.reload();
  await expect(page.getByText(`Reviewed · revision ${revision}`)).toBeVisible();
  await page.getByRole("link", { name: "Working brief" }).click();
  await expect(page.getByText("Left open by you")).toBeVisible();

  const constraints = row(page, "Constraints");
  await constraints.getByRole("button", { name: /^Correct:/ }).click();
  await constraints.getByLabel("Correct this statement").fill("Easy to use during a busy service.");
  await constraints.getByRole("button", { name: "Save correction" }).click();
  await expect(page.getByText(`Draft · revision ${revision + 1}`)).toBeVisible();
  await page.getByRole("link", { name: "Review and export" }).click();
  await expect(page.getByText(`Changed since reviewed revision ${revision}`)).toBeVisible();
  await expect(page.getByRole("link", { name: "Download Markdown (draft)" })).toBeVisible();
  await expect(page.getByTestId("reviewed-copies")).toContainText(`Revision ${revision}, reviewed`);
  const fixed = await (await request.get(`/api/projects/${id}/exports/json?revision=${revision}`)).json();
  expect(fixed.revision).toBe(revision);
});

test("a malformed model reading changes nothing and can be retried", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Fixture mode: canned responses, not a live model")).toBeVisible();
  const newButton = page.getByRole("button", { name: "New brief" });
  if (await newButton.isVisible()) await newButton.click();
  await page.getByRole("button", { name: "Malformed reading, then success" }).click();
  await page.getByRole("button", { name: "Read brief" }).click();
  const alert = page.getByRole("alert");
  await expect(alert).toContainText("did not pass validation, so nothing was changed");
  await expect(alert).toBeFocused();
  await alert.getByText("What failed validation").click();
  await expect(alert).toContainText("The response was not valid JSON.");
  await expect(page.getByRole("heading", { name: "Start from a brief" })).toBeVisible();
  await alert.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByRole("heading", { name: "Current understanding" })).toBeVisible();
  await expect(row(page, "Next step")).toContainText("Prepare a planning checklist.");
});
