import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { decision, fixtureStatus, project, question } from "@/test/factories";
import { WorkingBrief } from "./WorkingBrief";

function brief(p = project()) {
  const decide = vi.fn(async () => true);
  const reply = vi.fn(async () => true);
  const onReview = vi.fn();
  render(
    <WorkingBrief
      project={p}
      status={fixtureStatus}
      busy={false}
      workspace={{ decide, reply }}
      headingRef={{ current: null }}
      onReview={onReview}
    />,
  );
  return { decide, reply, onReview, user: userEvent.setup() };
}

describe("WorkingBrief", () => {
  it("shows statements with their basis, unknowns, open items, history, and sources", () => {
    brief();
    expect(screen.getByText("Help restaurants with incidents.")).toBeInTheDocument();
    expect(screen.getByText("From your brief: “Help restaurants”")).toBeInTheDocument();
    expect(screen.getByText("Not established")).toBeInTheDocument();
    expect(screen.getByText("Shown in the decision panel.")).toBeInTheDocument();
    expect(screen.getByText("Restaurants struggle with incidents.")).toBeInTheDocument();
    expect(screen.getByText("The release notes.")).toBeInTheDocument();
    expect(screen.getByText("From your brief: recorded 1 statement in your words.")).toBeInTheDocument();
    expect(screen.getByText("Help restaurants.")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "Which improvement should we investigate first?" }),
    ).toBeInTheDocument();
  });

  it("corrects and removes statements, and lets the next step rely on an assumption", async () => {
    const { decide, user } = brief();
    await user.click(screen.getByRole("button", { name: "Correct: Help restaurants with incidents." }));
    const field = screen.getByLabelText("Correct this statement");
    expect(screen.getByRole("button", { name: "Save correction" })).toBeDisabled();
    await user.clear(field);
    await user.type(field, "Help restaurants handle incidents.");
    await user.click(screen.getByRole("button", { name: "Save correction" }));
    expect(decide).toHaveBeenCalledWith(
      { type: "edit", itemId: "i1", text: "Help restaurants handle incidents." },
      "Saving your correction…",
    );

    await user.click(screen.getByRole("button", { name: "Remove: Help restaurants with incidents." }));
    const confirm = screen.getByRole("group", { name: "Confirm removing: Help restaurants with incidents." });
    await user.click(within(confirm).getByRole("button", { name: "Keep" }));
    await user.click(screen.getByRole("button", { name: "Remove: Help restaurants with incidents." }));
    const again = screen.getByRole("group", { name: "Confirm removing: Help restaurants with incidents." });
    await user.click(within(again).getByRole("button", { name: "Remove" }));
    expect(decide).toHaveBeenCalledWith({ type: "remove", itemId: "i1" }, "Removing the statement…");

    await user.click(screen.getByRole("button", { name: "Let the next step rely on this" }));
    expect(decide).toHaveBeenCalledWith(
      { type: "rely", itemId: "a1" },
      "Recording that the next step may rely on this…",
    );
  });

  it("cancels an unsaved correction", async () => {
    const { user } = brief();
    await user.click(screen.getByRole("button", { name: "Correct: Help restaurants with incidents." }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByLabelText("Correct this statement")).toBeNull();
  });

  it("brings an answered question back for correction and marks replaced decisions", async () => {
    const answered = question({
      status: "answered",
      resolution: {
        decisionId: "d2",
        summary: "Selected “Coordination during service”.",
        reason: null,
        via: "option",
        optionId: "q1.1",
      },
    });
    const { user } = brief(
      project({
        focusId: null,
        openQuestionCount: 0,
        questions: [answered],
        assumptions: project().assumptions.map((a) => ({ ...a, relied: true })),
        decisions: [
          decision({
            supersededBy: null,
            partlySupersededBy: [{ itemId: "q1", itemText: "Which improvement?", by: "d3" }],
          }),
          decision({
            id: "d2",
            action: "select",
            inputId: null,
            reason: "Busy.",
            supersededBy: "d3",
            summary: "Selected it.",
          }),
        ],
      }),
    );
    expect(screen.getByRole("heading", { name: "Nothing needs your answer now" })).toBeInTheDocument();
    expect(screen.getByText(/No questions are open\./)).toBeInTheDocument();
    expect(screen.getByText("You accepted this for the next step. It remains untested.")).toBeInTheDocument();
    expect(screen.getByText("Superseded by d3")).toBeInTheDocument();
    expect(screen.getByText("“Which improvement?” later changed by d3")).toBeInTheDocument();
    expect(screen.getByText("Reason: Busy.")).toBeInTheDocument();
    await user.click(screen.getByText("Answered questions (1)"));
    await user.click(screen.getByRole("button", { name: "Change answer" }));
    expect(screen.getByText("Change your answer")).toBeInTheDocument();
  });

  it("offers review when nothing needs an answer, and sends free-form instructions", async () => {
    const deferred = question({
      status: "deferred",
      actions: { select: true, answerInOwnWords: true, leaveOpen: false },
    });
    const { onReview, reply, user } = brief(
      project({ focusId: null, openQuestionCount: 1, questions: [deferred], assumptions: [], needed: [] }),
    );
    expect(screen.getByText(/1 question remains open/)).toBeInTheDocument();
    expect(screen.getByText("Left open by you")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Review the handoff" }));
    expect(onReview).toHaveBeenCalled();

    const box = screen.getByRole("textbox", { name: "Instruction or correction" });
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(screen.getByText("Write an instruction or correction first.")).toBeInTheDocument();
    await user.type(box, "The next step is interviews.");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(reply).toHaveBeenCalledWith("The next step is interviews.", null);

    await user.click(screen.getByRole("button", { name: "Answer this now" }));
    expect(screen.getByText("You left this open")).toBeInTheDocument();
  });
});
