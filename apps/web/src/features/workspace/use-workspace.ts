// Interaction state for the two surfaces. The API owns every domain transition; this hook only sends user
// actions, follows model operations to their persisted end, and shows the saved result.
import type { CurrentProjectView, Operation, ProjectView, RecoveryView, StatusView } from "@intent-harness/api-client";
import { useCallback, useEffect, useRef, useState } from "react";
import { type Api, type Decide, type Failure, RequestFailed } from "@/platform/api";
import type { WatchDeps } from "@/platform/watch-operation";
import { watchOperation } from "@/platform/watch-operation";
import { startedHere } from "./started-here";

export type Busy = { label: string; operationId: string | null; startedAt: number };
export type Problem = { message: string; issues: readonly string[]; retry?: () => void; reload?: boolean };
export type Phase = "loading" | "ready" | "load-failed";

export type WorkspaceDeps = { api: Api; watch: Omit<WatchDeps, "fetchOperation" | "eventsUrl">; now?: () => number };

export type Workspace = {
  phase: Phase;
  loadError: string | null;
  status: StatusView | null;
  project: ProjectView | null;
  recovery: RecoveryView | null;
  busy: Busy | null;
  problem: Problem | null;
  notice: string | null;
  /** Increments after each completed action so the decision area can take keyboard focus. */
  focusToken: number;
  reload(): void;
  createBrief(text: string): Promise<boolean>;
  reply(text: string, questionId: string | null): Promise<boolean>;
  decide(command: Decide, label: string, then?: "reassess"): Promise<boolean>;
  review(): Promise<boolean>;
  cancel(): Promise<void>;
  dismiss(): void;
};

const problemFrom = (f: Failure, retry?: () => void, prefix = ""): Problem => ({
  message: prefix + f.message,
  issues: f.issues,
  ...(f.retryable && retry ? { retry } : {}),
  ...(f.kind === "conflict" ? { reload: true } : {}),
});

const unexpected = (e: unknown): Failure =>
  e instanceof RequestFailed
    ? e.failure
    : { message: String(e), kind: "client", retryable: false, issues: [], activeOperationId: null };

/** What identifies a model request: the same fields on a running operation mean the same work. */
type Request = Pick<Operation, "kind" | "projectId" | "baseRevision" | "questionId" | "text">;

function isRequest(op: Operation, request: Request): boolean {
  return (
    op.kind === request.kind &&
    op.projectId === request.projectId &&
    op.baseRevision === request.baseRevision &&
    op.questionId === request.questionId &&
    op.text === (request.text?.trim() ?? null) // the API stores text trimmed
  );
}

export function useWorkspace({ api, watch, now = Date.now }: WorkspaceDeps): Workspace {
  const [phase, setPhase] = useState<Phase>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusView | null>(null);
  const [project, setProject] = useState<ProjectView | null>(null);
  const [recovery, setRecovery] = useState<RecoveryView | null>(null);
  const [busy, setBusy] = useState<Busy | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [focusToken, setFocusToken] = useState(0);
  const [reloads, setReloads] = useState(0);
  const projectRef = useRef<ProjectView | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const show = useCallback((next: ProjectView | null) => {
    projectRef.current = next;
    setProject(next);
  }, []);

  const follow = useCallback(
    (operationId: string, signal: AbortSignal): Promise<Operation> =>
      watchOperation(
        operationId,
        () => undefined,
        { ...watch, fetchOperation: api.operation, eventsUrl: api.eventsUrl },
        signal,
      ),
    [api, watch],
  );

  /** Start model work and follow it to its persisted end. Returns the operation only if it succeeded. */
  const operate = useCallback(
    async (
      label: string,
      start: () => Promise<Operation>,
      retry?: () => void,
      prefix = "",
    ): Promise<Operation | null> => {
      const controller = new AbortController();
      abortRef.current = controller;
      setBusy({ label, operationId: null, startedAt: now() });
      setProblem(null);
      setNotice(null);
      try {
        const started = await start();
        setBusy({ label, operationId: started.id, startedAt: now() });
        startedHere.add(started.id);
        const done = await follow(started.id, controller.signal);
        startedHere.remove(started.id); // finished; an aborted follow keeps it, so a reload can resume it
        if (done.status === "succeeded") return done;
        const error = done.error ?? { message: "The operation did not finish.", kind: "internal", retryable: true };
        if (done.status === "cancelled")
          setNotice(error.message); // the user asked for this; it is not a failure
        else setProblem(problemFrom({ ...error, issues: error.issues ?? [], activeOperationId: null }, retry, prefix));
        return null;
      } catch (e) {
        if (!controller.signal.aborted) setProblem(problemFrom(unexpected(e), retry, prefix));
        return null;
      } finally {
        abortRef.current = null;
        setBusy(null);
      }
    },
    [follow, now],
  );

  /** Starts a request. If the server is busy running exactly this request, for example one sent before a
   *  reload, follows that instead. A different request, such as another tab's, is reported as busy. */
  const send = useCallback(
    async (request: Request, start: () => Promise<Operation>): Promise<Operation> => {
      try {
        return await start();
      } catch (e) {
        const f = unexpected(e);
        if (f.kind !== "busy" || !f.activeOperationId) throw e;
        const running = await api.operation(f.activeOperationId);
        if (!isRequest(running, request)) throw e;
        return running;
      }
    },
    [api],
  );

  const refresh = useCallback(
    async (projectId: string, notes: readonly string[], fallback: string): Promise<ProjectView> => {
      const next = await api.project(projectId);
      show(next);
      const focus = next.questions.find((q) => q.id === next.focusId);
      setNotice([focus ? `New question: ${focus.text}` : fallback, ...notes].join(" "));
      setFocusToken((n) => n + 1);
      return next;
    },
    [api, show],
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: `reloads` is the trigger that reruns this load.
  useEffect(() => {
    let cancelled = false;
    setPhase("loading");
    Promise.all([api.status(), api.current(), api.activeOperations()]).then(
      async ([s, current, active]: [StatusView, CurrentProjectView, Operation[]]) => {
        if (cancelled) return;
        setStatus(s);
        show(current.project);
        setRecovery(current.recovery);
        setLoadError(null);
        setPhase("ready");
        // Only work on the brief shown, or work this tab started: another window's must not replace it.
        const shown = current.project?.id;
        const running = active.find((op) => (shown !== undefined && op.projectId === shown) || startedHere.has(op.id));
        if (running) {
          const done = await operate("Finishing work that was already running…", () => Promise.resolve(running));
          if (done?.result && !cancelled)
            await refresh(done.result.projectId, done.result.notes, "Earlier work finished.");
        }
      },
      (e: unknown) => {
        if (cancelled) return;
        setLoadError(unexpected(e).message);
        setPhase("load-failed");
      },
    );
    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
  }, [api, operate, refresh, show, reloads]);

  const reload = useCallback(() => {
    setProblem(null);
    setNotice(null);
    setReloads((n) => n + 1);
  }, []);

  const modelName = status?.mode === "fixture" ? "fixture responses" : (status?.model ?? "the model");

  const createBrief = useCallback(
    async (text: string): Promise<boolean> => {
      const request: Request = { kind: "create", projectId: null, baseRevision: null, questionId: null, text };
      const done = await operate(
        `Reading your brief with ${modelName}…`,
        () => send(request, () => api.create(text)),
        () => void createBrief(text),
      );
      if (!done?.result) return false;
      setRecovery(null);
      await refresh(done.result.projectId, done.result.notes, "Brief read. Check the statements and their sources.");
      return true;
    },
    [api, modelName, operate, refresh, send],
  );

  const reply = useCallback(
    async (text: string, questionId: string | null): Promise<boolean> => {
      const current = projectRef.current;
      if (!current) return false;
      const request: Request = {
        kind: "reply",
        projectId: current.id,
        baseRevision: current.revision,
        questionId,
        text,
      };
      const done = await operate(
        "Reading your words…",
        () => send(request, () => api.reply(current, text, questionId)),
        () => void reply(text, questionId),
      );
      if (!done?.result) return false;
      await refresh(done.result.projectId, done.result.notes, "Your words are recorded.");
      return true;
    },
    [api, operate, refresh, send],
  );

  const reassess = useCallback(
    async (after: ProjectView): Promise<void> => {
      const request: Request = {
        kind: "reassess",
        projectId: after.id,
        baseRevision: after.revision,
        questionId: null,
        text: null,
      };
      const done = await operate(
        "Checking whether anything else needs your input…",
        () => send(request, () => api.assess(after)),
        () => void reassess(projectRef.current ?? after),
        "Your choice is saved. The follow-up check failed: ",
      );
      if (done?.result)
        await refresh(done.result.projectId, done.result.notes, "Choice saved. Nothing else needs your answer now.");
    },
    [api, operate, refresh, send],
  );

  const command = useCallback(
    async (label: string, send: (p: ProjectView) => Promise<ProjectView>): Promise<ProjectView | null> => {
      const current = projectRef.current;
      if (!current) return null;
      setBusy({ label, operationId: null, startedAt: now() });
      setProblem(null);
      setNotice(null);
      try {
        const next = await send(current);
        show(next);
        setFocusToken((n) => n + 1);
        return next;
      } catch (e) {
        setProblem(problemFrom(unexpected(e)));
        return null;
      } finally {
        setBusy(null);
      }
    },
    [now, show],
  );

  const decide = useCallback(
    async (decision: Decide, label: string, then?: "reassess"): Promise<boolean> => {
      const next = await command(label, (p) => api.decide(p, decision));
      if (!next) return false;
      if (then === "reassess") await reassess(next);
      else setNotice("Saved.");
      return true;
    },
    [api, command, reassess],
  );

  const review = useCallback(async (): Promise<boolean> => {
    const next = await command("Marking this revision reviewed…", (p) => api.review(p));
    if (next) setNotice(`Revision ${next.revision} is reviewed.`);
    return next !== null;
  }, [api, command]);

  const cancel = useCallback(async () => {
    const id = busy?.operationId;
    if (id) await api.cancel(id).catch(() => undefined);
  }, [api, busy]);

  const dismiss = useCallback(() => setProblem(null), []);

  return {
    phase,
    loadError,
    status,
    project,
    recovery,
    busy,
    problem,
    notice,
    focusToken,
    reload,
    createBrief,
    reply,
    decide,
    review,
    cancel,
    dismiss,
  };
}
