import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { RequestFailed } from "@/platform/api";
import { fakeApi, fixtureStatus, operation, project } from "@/test/factories";
import { streams } from "@/test/streams";
import { useWorkspace, type WorkspaceDeps } from "./use-workspace";

function setup(options: { current?: ReturnType<typeof project> | null; active?: ReturnType<typeof operation>[] } = {}) {
  const api = fakeApi();
  const s = streams();
  api.status.mockResolvedValue(fixtureStatus);
  api.current.mockResolvedValue(
    options.current
      ? { state: "ready", project: options.current, recovery: null }
      : { state: "empty", project: null, recovery: null },
  );
  api.activeOperations.mockResolvedValue(options.active ?? []);
  const deps: WorkspaceDeps = { api, watch: { openStream: s.openStream, retryDelayMs: 1 }, now: () => 0 };
  const hook = renderHook(() => useWorkspace(deps));
  return { api, s, hook };
}

/** Finish the operation the hook is following with the given terminal state. */
async function finish(s: ReturnType<typeof streams>, terminal: ReturnType<typeof operation>) {
  await waitFor(() => expect(s.opened.length).toBeGreaterThan(0));
  act(() => s.latest().emit(terminal));
}

beforeEach(() => {
  sessionStorage.clear();
});

describe("useWorkspace", () => {
  it("loads an empty workspace", async () => {
    const { hook } = setup();
    await waitFor(() => expect(hook.result.current.phase).toBe("ready"));
    expect(hook.result.current.project).toBeNull();
    expect(hook.result.current.status?.mode).toBe("fixture");
  });

  it("reports a failed load and retries on reload", async () => {
    const { api, hook } = setup();
    api.status.mockRejectedValueOnce(
      new RequestFailed({
        message: "Server down.",
        kind: "network",
        retryable: true,
        issues: [],
        activeOperationId: null,
      }),
    );
    // The first load already started with a resolved status; force a second load that fails, then a third that works.
    await waitFor(() => expect(hook.result.current.phase).toBe("ready"));
    act(() => hook.result.current.reload());
    await waitFor(() => expect(hook.result.current.phase).toBe("load-failed"));
    expect(hook.result.current.loadError).toBe("Server down.");
    act(() => hook.result.current.reload());
    await waitFor(() => expect(hook.result.current.phase).toBe("ready"));
  });

  it("creates a project through a model operation and shows the saved result", async () => {
    const { api, s, hook } = setup();
    await waitFor(() => expect(hook.result.current.phase).toBe("ready"));
    const created = project({ focusId: null });
    api.create.mockResolvedValue(operation());
    api.project.mockResolvedValue(created);
    let ok: Promise<boolean> = Promise.resolve(false);
    act(() => {
      ok = hook.result.current.createBrief("A brief.");
    });
    await waitFor(() => expect(hook.result.current.busy?.label).toBe("Reading your brief with fixture responses…"));
    await finish(
      s,
      operation({
        version: 3,
        status: "succeeded",
        result: { projectId: "p1", revision: 1, notes: ["Skipped a repeated open item."] },
      }),
    );
    await expect(ok).resolves.toBe(true);
    await waitFor(() => expect(hook.result.current.project).toEqual(created));
    expect(hook.result.current.notice).toBe(
      "Brief read. Check the statements and their sources. Skipped a repeated open item.",
    );
    expect(hook.result.current.busy).toBeNull();
    expect(hook.result.current.focusToken).toBe(1);
  });

  it("shows a failed operation with its issues and retries on request", async () => {
    const { api, s, hook } = setup();
    await waitFor(() => expect(hook.result.current.phase).toBe("ready"));
    api.create.mockResolvedValue(operation());
    act(() => void hook.result.current.createBrief("A brief."));
    await finish(
      s,
      operation({
        version: 2,
        status: "failed",
        error: { kind: "invalid-output", message: "Did not pass validation.", retryable: true, issues: ["Not JSON."] },
      }),
    );
    await waitFor(() => expect(hook.result.current.problem?.message).toBe("Did not pass validation."));
    expect(hook.result.current.problem?.issues).toEqual(["Not JSON."]);
    expect(hook.result.current.project).toBeNull();

    api.create.mockResolvedValue(operation({ id: "op2" }));
    api.project.mockResolvedValue(project());
    act(() => hook.result.current.problem?.retry?.());
    await finish(
      s,
      operation({ id: "op2", version: 3, status: "succeeded", result: { projectId: "p1", revision: 1, notes: [] } }),
    );
    await waitFor(() => expect(hook.result.current.project?.id).toBe("p1"));
    expect(hook.result.current.notice).toBe("New question: Which improvement should we investigate first?");
  });

  it("follows the operation already running instead of starting another", async () => {
    const { api, s, hook } = setup({ current: project() });
    await waitFor(() => expect(hook.result.current.phase).toBe("ready"));
    api.reply.mockRejectedValue(
      new RequestFailed({ message: "Busy.", kind: "busy", retryable: false, issues: [], activeOperationId: "op9" }),
    );
    api.operation.mockResolvedValue(
      operation({
        id: "op9",
        kind: "reply",
        projectId: "p1",
        baseRevision: 1,
        questionId: "q1",
        text: "Coordination first.",
        status: "running",
        version: 2,
      }),
    );
    api.project.mockResolvedValue(project({ revision: 2 }));
    act(() => void hook.result.current.reply("Coordination first. ", "q1")); // the same request, sent again
    await finish(
      s,
      operation({ id: "op9", version: 3, status: "succeeded", result: { projectId: "p1", revision: 2, notes: [] } }),
    );
    await waitFor(() => expect(hook.result.current.project?.revision).toBe(2));
    expect(s.latest().url).toBe("/api/operations/op9/events");
  });

  it("never takes another tab's different request as its own when the server is busy", async () => {
    const { api, s, hook } = setup({ current: project() });
    await waitFor(() => expect(hook.result.current.phase).toBe("ready"));
    const busy = new RequestFailed({
      message: "The model is already working on this.",
      kind: "busy",
      retryable: false,
      issues: [],
      activeOperationId: "op9",
    });
    api.create.mockRejectedValue(busy);
    api.reply.mockRejectedValue(busy);
    api.operation.mockResolvedValueOnce(operation({ id: "op9", text: "Another tab's brief.", status: "running" }));
    await expect(hook.result.current.createBrief("My brief.")).resolves.toBe(false);
    api.operation.mockResolvedValueOnce(
      operation({ id: "op9", kind: "reply", projectId: "p1", baseRevision: 1, questionId: "q1", text: "Their reply." }),
    );
    await expect(hook.result.current.reply("My reply.", "q1")).resolves.toBe(false);
    await waitFor(() => expect(hook.result.current.problem?.message).toBe("The model is already working on this."));
    expect(s.opened).toHaveLength(0);
    expect(sessionStorage.getItem("zigzag:started-operations")).toBeNull();
  });

  it("saves a choice, then reassesses; a failed reassessment keeps the saved choice", async () => {
    const { api, s, hook } = setup({ current: project() });
    await waitFor(() => expect(hook.result.current.phase).toBe("ready"));
    const chosen = project({ revision: 2, focusId: null });
    api.decide.mockResolvedValue(chosen);
    api.assess.mockResolvedValue(operation({ kind: "reassess", projectId: "p1" }));
    act(
      () =>
        void hook.result.current.decide(
          { type: "select", questionId: "q1", optionId: "q1.1", reason: null },
          "Recording…",
          "reassess",
        ),
    );
    await finish(
      s,
      operation({
        version: 2,
        status: "failed",
        error: { kind: "model-unavailable", message: "Gateway down.", retryable: true },
      }),
    );
    await waitFor(() =>
      expect(hook.result.current.problem?.message).toBe(
        "Your choice is saved. The follow-up check failed: Gateway down.",
      ),
    );
    expect(hook.result.current.project).toEqual(chosen);
    expect(api.decide).toHaveBeenCalledWith(project(), {
      type: "select",
      questionId: "q1",
      optionId: "q1.1",
      reason: null,
    });
  });

  it("offers a reload after a conflicting command, and saves plain commands", async () => {
    const { api, hook } = setup({ current: project() });
    await waitFor(() => expect(hook.result.current.phase).toBe("ready"));
    api.decide.mockRejectedValueOnce(
      new RequestFailed({ message: "Stale.", kind: "conflict", retryable: false, issues: [], activeOperationId: null }),
    );
    await act(async () => {
      await hook.result.current.decide({ type: "rely", itemId: "a1" }, "Saving…");
    });
    expect(hook.result.current.problem).toMatchObject({ message: "Stale.", reload: true });
    act(() => hook.result.current.dismiss());
    expect(hook.result.current.problem).toBeNull();

    api.decide.mockResolvedValueOnce(project({ revision: 2 }));
    await act(async () => {
      await hook.result.current.decide({ type: "rely", itemId: "a1" }, "Saving…");
    });
    expect(hook.result.current.notice).toBe("Saved.");

    api.review.mockResolvedValueOnce(project({ revision: 2, status: "reviewed" }));
    await act(async () => {
      await hook.result.current.review();
    });
    expect(hook.result.current.notice).toBe("Revision 2 is reviewed.");
  });

  it("cancels the operation in progress", async () => {
    const { api, s, hook } = setup({ current: project() });
    await waitFor(() => expect(hook.result.current.phase).toBe("ready"));
    api.assess.mockResolvedValue(operation({ id: "op5", kind: "reassess" }));
    api.cancel.mockResolvedValue(operation({ id: "op5", status: "cancelled" }));
    api.decide.mockResolvedValue(project({ revision: 2 }));
    act(
      () =>
        void hook.result.current.decide({ type: "defer", questionId: "q1", reason: null }, "Deferring…", "reassess"),
    );
    await waitFor(() => expect(hook.result.current.busy?.operationId).toBe("op5"));
    await act(async () => {
      await hook.result.current.cancel();
    });
    expect(api.cancel).toHaveBeenCalledWith("op5");
    await finish(
      s,
      operation({
        id: "op5",
        version: 3,
        status: "cancelled",
        error: { kind: "cancelled", message: "Cancelled. Nothing was changed.", retryable: true },
      }),
    );
    await waitFor(() => expect(hook.result.current.notice).toBe("Cancelled. Nothing was changed."));
    expect(hook.result.current.problem).toBeNull();
  });

  it("resumes following work that was running when the page loaded", async () => {
    const running = operation({ id: "op7", kind: "reply", projectId: "p1", status: "running", version: 2 });
    const { api, s, hook } = setup({ current: project(), active: [running] });
    api.project.mockResolvedValue(project({ revision: 2, focusId: null }));
    await finish(
      s,
      operation({ id: "op7", version: 3, status: "succeeded", result: { projectId: "p1", revision: 2, notes: [] } }),
    );
    await waitFor(() => expect(hook.result.current.project?.revision).toBe(2));
    expect(hook.result.current.notice).toBe("Earlier work finished.");
  });

  it("leaves another window's work alone, so it cannot replace the brief shown", async () => {
    const elsewhere = operation({ id: "op8", kind: "reply", projectId: "p2", status: "running", version: 2 });
    const creating = operation({ id: "op9", kind: "create", projectId: null, status: "running", version: 2 });
    const { api, s, hook } = setup({ current: project(), active: [elsewhere, creating] });
    await waitFor(() => expect(hook.result.current.phase).toBe("ready"));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(s.opened).toHaveLength(0);
    expect(hook.result.current.busy).toBeNull();
    expect(api.project).not.toHaveBeenCalled();
    expect(hook.result.current.project?.id).toBe("p1");
  });

  it("resumes its own work after a reload, even for another brief", async () => {
    const { api, s, hook } = setup();
    await waitFor(() => expect(hook.result.current.phase).toBe("ready"));
    api.create.mockResolvedValue(operation({ id: "op9" }));
    void hook.result.current.createBrief("Brief.");
    await waitFor(() => expect(s.opened.length).toBe(1));
    expect(JSON.parse(sessionStorage.getItem("zigzag:started-operations") ?? "[]")).toEqual(["op9"]);
    hook.unmount(); // the tab reloads while the brief is being read

    const after = setup({ current: project({ id: "p2" }), active: [operation({ id: "op9", status: "running" })] });
    after.api.project.mockResolvedValue(project({ id: "p3", focusId: null }));
    await finish(
      after.s,
      operation({ id: "op9", version: 3, status: "succeeded", result: { projectId: "p3", revision: 1, notes: [] } }),
    );
    await waitFor(() => expect(after.hook.result.current.project?.id).toBe("p3"));
    expect(sessionStorage.getItem("zigzag:started-operations")).toBe("[]");
  });

  it("does nothing without a project", async () => {
    const { hook } = setup();
    await waitFor(() => expect(hook.result.current.phase).toBe("ready"));
    await expect(hook.result.current.reply("x", null)).resolves.toBe(false);
    await expect(hook.result.current.decide({ type: "rely", itemId: "a1" }, "x")).resolves.toBe(false);
    await expect(hook.result.current.review()).resolves.toBe(false);
  });
});
