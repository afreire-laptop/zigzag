import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CurrentProjectView } from "@zigzag/api-client";
import { beforeEach, describe, expect, it } from "vitest";
import type { WorkspaceDeps } from "@/features/workspace/use-workspace";
import { RequestFailed } from "@/platform/api";
import { fakeApi, fixtureStatus, handoff, operation, project } from "@/test/factories";
import { streams } from "@/test/streams";
import { App } from "./App";

function start(current: CurrentProjectView, status = fixtureStatus) {
  const api = fakeApi();
  const s = streams();
  api.status.mockResolvedValue(status);
  api.current.mockResolvedValue(current);
  api.activeOperations.mockResolvedValue([]);
  api.handoff.mockResolvedValue(handoff());
  const deps: WorkspaceDeps = { api, watch: { openStream: s.openStream }, now: () => 0 };
  render(<App deps={deps} />);
  return { api, s, user: userEvent.setup() };
}

beforeEach(() => {
  window.location.hash = "";
});

describe("App", () => {
  it("starts from a brief when nothing is saved, then opens the working brief", async () => {
    const { api, s, user } = start({ state: "empty", project: null, recovery: null });
    expect(screen.getByText("Loading…")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Start from a brief" })).toBeInTheDocument();
    expect(screen.getByText("Fixture mode: canned responses, not a live model")).toBeInTheDocument();
    api.create.mockResolvedValue(operation());
    api.project.mockResolvedValue(project());
    await user.type(screen.getByLabelText("Brief"), "Help restaurants.");
    await user.click(screen.getByRole("button", { name: "Read brief" }));
    await waitFor(() => expect(s.opened).toHaveLength(1));
    s.latest().emit(
      operation({ version: 3, status: "succeeded", result: { projectId: "p1", revision: 1, notes: [] } }),
    );
    expect(await screen.findByRole("heading", { name: "Current understanding" })).toBeInTheDocument();
    expect(screen.getByText("Draft · revision 1")).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 2, name: "Which improvement should we investigate first?" }),
      ).toHaveFocus(),
    );
  });

  it("replaces a shown project with a newly created one and focuses its decision area", async () => {
    const { api, s, user } = start({ state: "ready", project: project({ id: "old" }), recovery: null });
    await user.click(await screen.findByRole("button", { name: "New brief" }));
    api.create.mockResolvedValue(operation());
    api.project.mockResolvedValue(project({ id: "new", focusId: null, questions: [] }));
    await user.type(screen.getByLabelText("Brief"), "Another brief.");
    await user.click(screen.getByRole("button", { name: "Read brief" }));
    await waitFor(() => expect(s.opened).toHaveLength(1));
    s.latest().emit(
      operation({ version: 3, status: "succeeded", result: { projectId: "new", revision: 1, notes: [] } }),
    );
    await waitFor(() => expect(screen.getByRole("heading", { name: "Nothing needs your answer now" })).toHaveFocus());
  });

  it("moves between the two surfaces and back to a new brief", async () => {
    const { user } = start({ state: "ready", project: project(), recovery: null });
    expect(await screen.findByRole("link", { name: "Working brief" })).toHaveAttribute("aria-current", "page");
    await user.click(screen.getByRole("link", { name: "Review and export" }));
    expect(await screen.findByRole("heading", { name: "Handoff status" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review and export" })).toHaveAttribute("aria-current", "page");
    await user.click(screen.getByRole("button", { name: "New brief" }));
    expect(screen.getByRole("heading", { name: "Start from a brief" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to current brief" }));
    expect(await screen.findByRole("heading", { name: "Current understanding" })).toBeInTheDocument();
  });

  it("names the live model and shows a damaged record instead of an older project", async () => {
    start(
      {
        state: "corrupt",
        project: null,
        recovery: {
          projectId: "p9",
          file: "data/projects/p9.json",
          reason: "bad",
          modifiedAt: "2026-10-06T10:00:00.000Z",
        },
      },
      {
        mode: "live",
        model: "anthropic/claude-opus-5.5",
        reasoningEffort: "high",
        promptVersion: "assess-v2",
        fixtures: null,
        damagedOperations: [],
      },
    );
    expect(await screen.findByText("Live model: anthropic/claude-opus-5.5 · prompt assess-v2")).toBeInTheDocument();
    expect(screen.getByText("The most recent saved project could not be opened.")).toBeInTheDocument();
  });

  it("says model work is paused while an operation record cannot be read, and names the file", async () => {
    start(
      { state: "empty", project: null, recovery: null },
      {
        ...fixtureStatus,
        damagedOperations: [
          { file: "data/operations/op-z.json", reason: "file: Invalid JSON", modifiedAt: "2026-10-06T10:00:00.000Z" },
        ],
      },
    );
    expect(await screen.findByText("Model work is paused: an operation record cannot be read.")).toBeInTheDocument();
    expect(screen.getByText("data/operations/op-z.json")).toBeInTheDocument();
  });

  it("offers a retry when loading fails", async () => {
    const api = fakeApi();
    api.status.mockRejectedValueOnce(
      new RequestFailed({
        message: "Server down.",
        kind: "network",
        retryable: true,
        issues: [],
        activeOperationId: null,
      }),
    );
    api.status.mockResolvedValue(fixtureStatus);
    api.current.mockResolvedValue({ state: "empty", project: null, recovery: null });
    api.activeOperations.mockResolvedValue([]);
    render(<App deps={{ api, watch: { openStream: streams().openStream } }} />);
    expect(await screen.findByText("Could not load your work: Server down.")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Start from a brief" })).toBeInTheDocument();
  });
});
