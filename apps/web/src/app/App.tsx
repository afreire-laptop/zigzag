import type { StatusView } from "@intent-harness/api-client";
import { useEffect, useRef, useState } from "react";
import { StatusPill } from "@/design-system/status-pill";
import { Alert, AlertDescription, AlertTitle } from "@/design-system/ui/alert";
import { Button } from "@/design-system/ui/button";
import { Intake } from "@/features/intake/Intake";
import { ReviewSurface } from "@/features/review/ReviewSurface";
import { WorkingBrief } from "@/features/working-brief/WorkingBrief";
import { useWorkspace, type WorkspaceDeps } from "@/features/workspace/use-workspace";
import { ActivityBar } from "./ActivityBar";
import { useSurface } from "./use-surface";

export function App({ deps }: { deps: WorkspaceDeps }) {
  const workspace = useWorkspace(deps);
  const { status, project, busy, phase } = workspace;
  const [surface, setSurface] = useSurface();
  // The project shown when "New brief" was chosen. A newly created project has another id, so the form
  // gives way to it in the same render that asks for focus.
  const [composingFrom, setComposingFrom] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement | null>(null);
  const now = deps.now ?? Date.now;

  const showIntake = !project || composingFrom === project.id;

  // After each completed action, keyboard focus moves to the decision area instead of being lost.
  useEffect(() => {
    if (workspace.focusToken > 0 && !showIntake) headingRef.current?.focus({ preventScroll: true });
  }, [workspace.focusToken, showIntake]);

  if (phase === "loading") return <p className="mx-auto my-16 max-w-xl px-4">Loading…</p>;
  if (phase === "load-failed") {
    return (
      <div className="mx-auto my-16 max-w-xl space-y-3 px-4" role="alert">
        <p>Could not load your work: {workspace.loadError}</p>
        <Button onClick={workspace.reload}>Retry</Button>
      </div>
    );
  }

  const isBusy = Boolean(busy);

  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-10 focus:rounded focus:bg-background focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="border-b bg-card">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <span className="font-bold">Intent Harness</span>
          {project && !showIntake && (
            <nav aria-label="Surfaces" className="flex gap-1">
              {(
                [
                  ["brief", "Working brief"],
                  ["review", "Review and export"],
                ] as const
              ).map(([key, label]) => (
                <a
                  key={key}
                  href={`#${key}`}
                  aria-current={surface === key ? "page" : undefined}
                  className="rounded-full px-3 py-1.5 text-sm font-semibold text-muted-foreground aria-[current=page]:bg-muted aria-[current=page]:text-foreground"
                >
                  {label}
                </a>
              ))}
            </nav>
          )}
          <ModeBadge status={status} />
        </div>
      </header>

      <ActivityBar
        busy={busy}
        notice={workspace.notice}
        problem={workspace.problem}
        now={now}
        onCancel={() => void workspace.cancel()}
        onReload={workspace.reload}
        onDismiss={workspace.dismiss}
      />

      <main id="main" className="mx-auto max-w-6xl px-4 pb-16">
        <DamagedOperations status={status} />
        {showIntake ? (
          <Intake
            status={status}
            recovery={workspace.recovery}
            busy={isBusy}
            onSubmit={workspace.createBrief}
            onCancel={project ? () => setComposingFrom(null) : undefined}
          />
        ) : (
          <>
            <div className="my-6 flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Brief</p>
                <h1 className="max-w-3xl text-2xl font-semibold tracking-tight">{project.title}</h1>
              </div>
              <div className="flex items-center gap-2">
                <StatusPill reviewed={project.status === "reviewed"} revision={project.revision} />
                <Button
                  variant="ghost"
                  onClick={() => {
                    setSurface("brief");
                    setComposingFrom(project.id);
                  }}
                  disabled={isBusy}
                >
                  New brief
                </Button>
              </div>
            </div>
            {surface === "brief" ? (
              <WorkingBrief
                project={project}
                status={status}
                busy={isBusy}
                workspace={workspace}
                headingRef={headingRef}
                onReview={() => setSurface("review")}
              />
            ) : (
              <ReviewSurface project={project} busy={isBusy} api={deps.api} onReview={workspace.review} />
            )}
          </>
        )}
      </main>
    </>
  );
}

/** Shown while the API refuses model work because an operation record cannot be read. */
function DamagedOperations({ status }: { status: StatusView | null }) {
  if (!status?.damagedOperations.length) return null;
  return (
    <Alert className="mt-4 border-warning-foreground/40 bg-warning text-warning-foreground">
      <AlertTitle>Model work is paused: an operation record cannot be read.</AlertTitle>
      <AlertDescription className="text-warning-foreground">
        <ul>
          {status.damagedOperations.map((d) => (
            <li key={d.file}>
              <code className="break-all">{d.file}</code> ({d.reason})
            </li>
          ))}
        </ul>
        <p className="mt-1">
          Whether its work reached the brief is unknown, so it was left untouched. Check the brief, then move the file
          out of the data directory and reload.
        </p>
      </AlertDescription>
    </Alert>
  );
}

function ModeBadge({ status }: { status: StatusView | null }) {
  if (!status) return null;
  return status.mode === "fixture" ? (
    <span className="ml-auto rounded-full border border-warning-foreground bg-warning px-3 py-1 text-sm font-bold text-warning-foreground">
      Fixture mode: canned responses, not a live model
    </span>
  ) : (
    <span className="ml-auto rounded-full border px-3 py-1 text-sm text-muted-foreground">
      Live model: {status.model}
      {status.promptVersion ? ` · prompt ${status.promptVersion}` : ""}
    </span>
  );
}
