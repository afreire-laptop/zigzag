import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { fixtureStatus } from "@/test/factories";
import { Intake } from "./Intake";

it("validates, inserts fixture texts, submits, and explains a damaged record", async () => {
  const onSubmit = vi.fn(async () => true);
  const onCancel = vi.fn();
  const user = userEvent.setup();
  render(
    <Intake
      status={fixtureStatus}
      recovery={{
        projectId: "p9",
        file: "data/projects/p9.json",
        reason: "revision: not an integer",
        modifiedAt: "2026-10-06T10:00:00.000Z",
      }}
      busy={false}
      onSubmit={onSubmit}
      onCancel={onCancel}
    />,
  );
  expect(screen.getByText("The most recent saved project could not be opened.")).toBeInTheDocument();
  expect(screen.getByText("data/projects/p9.json")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Read brief" }));
  expect(screen.getByText("Paste or write a brief first.")).toBeInTheDocument();
  expect(screen.getByLabelText("Brief")).toHaveAttribute("aria-invalid", "true");
  await user.click(screen.getByRole("button", { name: "Clear brief" }));
  await user.click(screen.getByRole("button", { name: "Read brief" }));
  expect(onSubmit).toHaveBeenCalledWith("Clear brief text.");
  await user.click(screen.getByRole("button", { name: "Back to current brief" }));
  expect(onCancel).toHaveBeenCalled();
});
