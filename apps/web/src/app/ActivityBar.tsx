import { useEffect, useRef, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/design-system/ui/alert";
import { Button } from "@/design-system/ui/button";
import type { Busy, Problem } from "@/features/workspace/use-workspace";

function Elapsed({ since, now }: { since: number; now: () => number }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setSeconds(Math.floor((now() - since) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [since, now]);
  return <span className="tabular-nums text-muted-foreground">{seconds}s</span>;
}

/** The live status line and the failure alert. Failures take focus so keyboard and screen reader users meet them. */
export function ActivityBar(props: {
  busy: Busy | null;
  notice: string | null;
  problem: Problem | null;
  now: () => number;
  onCancel: () => void;
  onReload: () => void;
  onDismiss: () => void;
}) {
  const { busy, notice, problem } = props;
  const alertRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (problem) alertRef.current?.focus();
  }, [problem]);

  return (
    <div className="mx-auto max-w-6xl px-4">
      <div
        role="status"
        aria-live="polite"
        className={busy || notice ? "mt-4 flex items-center gap-3 rounded-lg bg-muted px-4 py-2 text-sm" : "sr-only"}
      >
        {busy ? (
          <>
            <span
              aria-hidden="true"
              className="size-4 animate-spin rounded-full border-2 border-primary border-r-transparent"
            />
            <span>{busy.label}</span>
            {busy.operationId && (
              <>
                <Elapsed since={busy.startedAt} now={props.now} />
                <Button variant="outline" size="sm" className="ml-auto" onClick={props.onCancel}>
                  Cancel
                </Button>
              </>
            )}
          </>
        ) : (
          notice
        )}
      </div>
      {problem && (
        <Alert variant="destructive" ref={alertRef} tabIndex={-1} className="mt-4" role="alert">
          <AlertTitle>{problem.message}</AlertTitle>
          <AlertDescription>
            {problem.issues.length > 0 && (
              <details className="mt-1">
                <summary className="cursor-pointer">What failed validation</summary>
                <ul className="mt-1 list-disc pl-5">
                  {problem.issues.map((issue) => (
                    <li key={issue}>{issue}</li>
                  ))}
                </ul>
              </details>
            )}
            <div className="mt-2 flex flex-wrap gap-2">
              {problem.retry && (
                <Button size="sm" onClick={problem.retry} disabled={Boolean(busy)}>
                  Retry
                </Button>
              )}
              {problem.reload && (
                <Button size="sm" variant="outline" onClick={props.onReload}>
                  Reload saved state
                </Button>
              )}
              <Button size="sm" variant="ghost" onClick={props.onDismiss}>
                Dismiss
              </Button>
            </div>
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}
