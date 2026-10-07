import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { question } from "@/test/factories";
import { DecisionPanel } from "./DecisionPanel";

function panel(q = question(), options: { isFocus?: boolean; busy?: boolean } = {}) {
  const decide = vi.fn(async () => true);
  const reply = vi.fn(async () => true);
  const view = render(
    <DecisionPanel
      question={q}
      isFocus={options.isFocus ?? true}
      busy={options.busy ?? false}
      decide={decide}
      reply={reply}
      fixtureReplies={[{ label: "Short reply", text: "Coordination first." }]}
      headingRef={{ current: null }}
    />,
  );
  return { decide, reply, view, user: userEvent.setup() };
}

describe("DecisionPanel", () => {
  it("proposes options with none preselected and records the chosen one with a reason", async () => {
    const { decide, user } = panel();
    expect(screen.getByText("Needs your decision")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "Which improvement should we investigate first?" }),
    ).toBeInTheDocument();
    const radios = screen.getAllByRole("radio");
    for (const radio of radios) expect(radio).not.toBeChecked();
    await user.click(screen.getByRole("button", { name: "Record choice" }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Choose a direction, write your own answer, or leave the question open.",
    );
    await user.click(screen.getByRole("radio", { name: /Coordination during service/ }));
    await user.type(screen.getByLabelText("Reason (optional)"), "Service hurts.");
    await user.click(screen.getByRole("button", { name: "Record choice" }));
    expect(decide).toHaveBeenCalledWith(
      { type: "select", questionId: "q1", optionId: "q1.1", reason: "Service hurts." },
      "Recording your choice…",
      "reassess",
    );
  });

  it("accepts an answer in the user's own words", async () => {
    const { reply, user } = panel();
    await user.click(screen.getByRole("radio", { name: /Something else/ }));
    await user.click(screen.getByRole("button", { name: "Send answer" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Write your answer first.");
    await user.click(screen.getByRole("button", { name: "Short reply" }));
    await user.click(screen.getByRole("button", { name: "Send answer" }));
    expect(reply).toHaveBeenCalledWith("Coordination first.", "q1");
  });

  it("leaves an open question open", async () => {
    const { decide, user } = panel(question({ deferEffect: null }), { isFocus: false });
    expect(screen.getByText("Open question")).toBeInTheDocument();
    expect(screen.getByText("The question stays open and is listed in the handoff as unresolved.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Leave this open" }));
    expect(decide).toHaveBeenCalledWith(
      { type: "defer", questionId: "q1", reason: null },
      "Recording that this stays open…",
      "reassess",
    );
  });

  it("offers every correction for an answer chosen from the options", async () => {
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
    const { decide, user } = panel(answered);
    expect(screen.getByText("Change your answer")).toBeInTheDocument();
    expect(screen.getByText(/Current answer: Selected/)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Coordination during service \(current answer\)/ })).toBeDisabled();
    expect(screen.getByRole("radio", { name: /Something else/ })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Withdraw answer and leave open" }));
    expect(decide).toHaveBeenCalledWith(
      { type: "defer", questionId: "q1", reason: null },
      "Withdrawing the answer and leaving it open…",
      "reassess",
    );
  });

  it("explains how to correct an answer given in the user's own words", () => {
    panel(
      question({
        status: "answered",
        resolution: {
          decisionId: "d2",
          summary: "From your reply: answered it.",
          reason: null,
          via: "ownWords",
          optionId: null,
        },
        actions: { select: false, answerInOwnWords: false, leaveOpen: true },
      }),
    );
    expect(screen.getByText(/Correct or remove those statements under Current understanding/)).toBeInTheDocument();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.getByRole("button", { name: "Withdraw answer and leave open" })).toBeInTheDocument();
  });

  it("shows a deferred question and its source quote; a question without options asks for words", async () => {
    const { reply, user } = panel(
      question({
        status: "deferred",
        options: [],
        sourceQuote: "I don't know whether",
        resolution: { decisionId: "d3", summary: "Left open: “Q”.", reason: null, via: "leftOpen", optionId: null },
        actions: { select: false, answerInOwnWords: true, leaveOpen: false },
      }),
    );
    expect(screen.getByText("You left this open")).toBeInTheDocument();
    expect(screen.getByText(/Your words: “I don't know whether”/)).toBeInTheDocument();
    expect(screen.getByText(/Left open: Left open/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Leave this open" })).toBeNull();
    await user.type(screen.getByLabelText("Your answer"), "Process first.");
    await user.click(screen.getByRole("button", { name: "Send answer" }));
    expect(reply).toHaveBeenCalledWith("Process first.", "q1");
  });
});
