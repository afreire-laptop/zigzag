import type { HandoffView, ProjectView } from "@intent-harness/api-client";
import { useEffect, useState } from "react";
import { formatTime, plural } from "@/design-system/lib/format";
import { Button } from "@/design-system/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/design-system/ui/card";
import type { Api } from "@/platform/api";
import { Markdown } from "./Markdown";

export function ReviewSurface(props: {
  project: ProjectView;
  busy: boolean;
  api: Pick<Api, "handoff" | "exportUrl">;
  onReview: () => Promise<boolean>;
}) {
  const { project, busy, api } = props;
  const [view, setView] = useState<HandoffView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reviewed = project.status === "reviewed";

  useEffect(() => {
    let cancelled = false;
    api.handoff(project.id).then(
      (v) => {
        if (cancelled) return;
        setView(v);
        setError(null);
      },
      (e: Error) => {
        if (!cancelled) setError(e.message);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, project]); // every saved change arrives as a new view, so the handoff is reloaded with it

  // Offer review only when the displayed document is exactly the saved revision.
  const current =
    view !== null && view.current.revision === project.revision && (view.current.status === "reviewed") === reviewed;
  const open = project.openQuestionCount;
  const label = reviewed ? "" : " (draft)";

  return (
    <div className="grid max-w-3xl gap-5">
      <Card aria-labelledby="review-heading">
        <CardHeader>
          <CardTitle>
            <h2 id="review-heading">Handoff status</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {reviewed ? (
            <p className="rounded-md bg-reviewed px-3 py-2 font-semibold text-reviewed-foreground">
              Revision {project.revision} is reviewed. Exports are the fixed copies saved at review time.
            </p>
          ) : (
            <p className="rounded-md bg-draft px-3 py-2 font-semibold text-draft-foreground">
              Revision {project.revision} is a draft.{" "}
              {view?.lastReviewed
                ? `The last reviewed revision is ${view.lastReviewed.revision}; changes saved since then are listed below.`
                : "It has not been reviewed."}{" "}
              Exports are labeled DRAFT until you review this revision.
            </p>
          )}
          {open > 0 && (
            <p>
              {open} {plural(open, "question remains", "questions remain")} open. Reviewing records{" "}
              {plural(open, "it", "them")} as open; it does not select an option.
            </p>
          )}
          {!project.hasNextStep && (
            <p className="rounded-md border-l-4 border-warning-foreground bg-warning px-3 py-2 text-warning-foreground">
              <strong>No next step is established.</strong> A reader of this handoff cannot tell what it permits. If you
              know the next step, add it as an instruction on the working brief, for example “The next step is
              interviews.”
            </p>
          )}
          <p className="text-sm text-muted-foreground">
            Read the whole handoff below. Review confirms it as the direction for its stated next step, not proof that
            the direction is right.
          </p>
          {view?.changes && view.changes.length > 0 && (
            <section aria-labelledby="changes-heading">
              <h3 id="changes-heading" className="font-semibold">
                Changed since reviewed revision {view.lastReviewed?.revision}
              </h3>
              <ul className="mt-1 list-disc pl-5">
                {view.changes.map((c) => (
                  <li key={c.section}>
                    <strong>{c.section}</strong>
                    <ul className="list-disc pl-5">
                      {c.removed.map((x) => (
                        <li key={`-${x}`} className="text-destructive">
                          <span className="sr-only">Removed: </span>
                          <del>{x}</del>
                        </li>
                      ))}
                      {c.added.map((x) => (
                        <li key={`+${x}`} className="text-reviewed-foreground">
                          <span className="sr-only">Added: </span>
                          {x}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </CardContent>
      </Card>

      <article
        className="rounded-xl border bg-card p-6 text-card-foreground"
        aria-label={`Handoff document, revision ${project.revision}`}
        data-testid="handoff"
      >
        {error ? (
          <p role="alert">Could not load the handoff: {error}</p>
        ) : view ? (
          <Markdown source={view.current.markdown} />
        ) : (
          <p>Loading…</p>
        )}
      </article>

      <Card aria-labelledby="export-heading">
        <CardHeader>
          <CardTitle>
            <h2 id="export-heading">{reviewed ? "Export" : "Mark reviewed and export"}</h2>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-center gap-2">
            {!reviewed && (
              <Button onClick={() => void props.onReview()} disabled={busy || !current}>
                Mark revision {project.revision} reviewed
              </Button>
            )}
            <Button variant="outline" asChild>
              <a href={api.exportUrl(project.id, "markdown")} download>
                Download Markdown{label}
              </a>
            </Button>
            <Button variant="outline" asChild>
              <a href={api.exportUrl(project.id, "json")} download>
                Download JSON{label}
              </a>
            </Button>
          </div>
          {view && view.reviews.length > 0 && (
            <>
              <h3 className="mt-4 text-sm font-semibold">Reviewed copies</h3>
              <ul className="mt-1 space-y-1 text-sm" data-testid="reviewed-copies">
                {[...view.reviews].reverse().map((r) => (
                  <li key={r.revision}>
                    Revision {r.revision}, reviewed {formatTime(r.reviewedAt)}:{" "}
                    <a
                      className="text-primary underline"
                      href={api.exportUrl(project.id, "markdown", r.revision)}
                      download
                    >
                      Markdown<span className="sr-only">, revision {r.revision}</span>
                    </a>{" "}
                    ·{" "}
                    <a className="text-primary underline" href={api.exportUrl(project.id, "json", r.revision)} download>
                      JSON<span className="sr-only">, revision {r.revision}</span>
                    </a>
                  </li>
                ))}
              </ul>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
