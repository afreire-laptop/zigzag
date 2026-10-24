import type { ProjectView } from "@zigzag/api-client";
import { Badge } from "@/design-system/ui/badge";
import { Button } from "@/design-system/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/design-system/ui/card";
import type { Workspace } from "@/features/workspace/use-workspace";

export function OpenItems(props: {
  project: ProjectView;
  busy: boolean;
  activeId: string | null;
  onPick: (questionId: string) => void;
  decide: Workspace["decide"];
}) {
  const { project, busy } = props;
  const open = project.questions.filter((q) => q.status !== "answered");
  const answered = project.questions.filter((q) => q.status === "answered");
  const heading = "mt-5 text-xs font-bold uppercase tracking-wide text-muted-foreground first:mt-0";
  const item = "border-t py-3 first:border-t-0";

  return (
    <Card aria-labelledby="open-heading">
      <CardHeader>
        <CardTitle>
          <h2 id="open-heading">Open items</h2>
        </CardTitle>
        <CardDescription>
          These stay visible in the handoff until you resolve them. Nothing here has been decided for you.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <h3 className={heading}>Questions</h3>
        {open.length === 0 ? (
          <p className="italic text-muted-foreground">No open questions.</p>
        ) : (
          <ul>
            {open.map((q) => (
              <li key={q.id} className={item}>
                <p className="font-semibold">
                  {q.text}{" "}
                  <Badge variant={q.status === "deferred" ? "secondary" : "outline"}>
                    {q.status === "deferred" ? "Left open by you" : "Not answered"}
                  </Badge>
                </p>
                <p className="text-sm text-muted-foreground">What it changes: {q.effect}</p>
                {q.id === props.activeId ? (
                  <p className="text-sm font-semibold">Shown in the decision panel.</p>
                ) : (
                  <Button
                    variant="link"
                    size="sm"
                    className="h-auto px-0"
                    onClick={() => props.onPick(q.id)}
                    disabled={busy}
                  >
                    Answer this now
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
        {answered.length > 0 && (
          <details className="mt-3">
            <summary className="cursor-pointer text-sm font-semibold">Answered questions ({answered.length})</summary>
            <ul>
              {answered.map((q) => (
                <li key={q.id} className={item}>
                  <p className="font-semibold">{q.text}</p>
                  <p className="text-sm text-muted-foreground">{q.resolution?.summary}</p>
                  {q.id !== props.activeId && (q.actions.select || q.actions.leaveOpen) && (
                    <Button
                      variant="link"
                      size="sm"
                      className="h-auto px-0"
                      onClick={() => props.onPick(q.id)}
                      disabled={busy}
                    >
                      Change answer
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </details>
        )}

        <h3 className={heading}>Assumptions</h3>
        {project.assumptions.length === 0 ? (
          <p className="italic text-muted-foreground">None recorded.</p>
        ) : (
          <ul>
            {project.assumptions.map((a) => (
              <li key={a.id} className={item}>
                <p className="font-semibold">
                  {a.text} <Badge className="bg-warning text-warning-foreground">Untested</Badge>
                </p>
                <p className="text-sm text-muted-foreground">Basis: {a.basis}</p>
                <p className="text-sm text-muted-foreground">Why it matters: {a.effect}</p>
                {a.relied ? (
                  <p className="text-sm font-semibold">You accepted this for the next step. It remains untested.</p>
                ) : (
                  <Button
                    variant="link"
                    size="sm"
                    className="h-auto px-0"
                    onClick={() =>
                      void props.decide(
                        { type: "rely", itemId: a.id },
                        "Recording that the next step may rely on this…",
                      )
                    }
                    disabled={busy}
                  >
                    Let the next step rely on this
                  </Button>
                )}
                <p className="mt-1 text-xs text-muted-foreground">Proposed by {a.proposedBy}.</p>
              </li>
            ))}
          </ul>
        )}

        <h3 className={heading}>Needed later</h3>
        {project.needed.length === 0 ? (
          <p className="italic text-muted-foreground">None recorded.</p>
        ) : (
          <ul>
            {project.needed.map((n) => (
              <li key={n.id} className={item}>
                <p className="font-semibold">{n.text}</p>
                <p className="text-sm text-muted-foreground">{n.effect}</p>
                <p className="text-sm text-muted-foreground">Basis: {n.basis}</p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
