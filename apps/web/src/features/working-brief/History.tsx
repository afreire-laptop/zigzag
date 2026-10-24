import type { DecisionView, InputView } from "@zigzag/api-client";
import { formatTime } from "@/design-system/lib/format";
import { Badge } from "@/design-system/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/design-system/ui/card";

export function History({ decisions }: { decisions: readonly DecisionView[] }) {
  return (
    <Card aria-labelledby="history-heading">
      <CardHeader>
        <CardTitle>
          <h2 id="history-heading">Decision history</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {decisions.length === 0 ? (
          <p className="italic text-muted-foreground">No decisions yet.</p>
        ) : (
          <ol data-testid="history">
            {decisions.map((d) => (
              <li key={d.id} className="grid gap-0.5 border-t py-2 first:border-t-0">
                <span className="text-xs text-muted-foreground">
                  {d.id} · {formatTime(d.at)} · revision {d.revision}
                </span>
                <span className={d.supersededBy ? "text-muted-foreground line-through" : undefined}>{d.summary}</span>
                <span className="text-sm text-muted-foreground">
                  {d.inputId
                    ? `In your own words (${d.inputId}, under “Your text”).`
                    : `Reason: ${d.reason ?? "not given"}`}
                </span>
                {d.supersededBy && <Badge variant="outline">Superseded by {d.supersededBy}</Badge>}
                {d.partlySupersededBy.map((part) => (
                  <Badge key={part.itemId} variant="outline" className="h-auto whitespace-normal">
                    “{part.itemText}” later changed by {part.by}
                  </Badge>
                ))}
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

export function Sources({ inputs }: { inputs: readonly InputView[] }) {
  return (
    <Card aria-labelledby="sources-heading">
      <CardHeader>
        <CardTitle>
          <h2 id="sources-heading">Your text</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {inputs.map((i) => (
          <figure key={i.id}>
            <figcaption className="text-xs text-muted-foreground">
              {i.kind === "brief" ? "Brief" : "Reply"} {i.id} · {formatTime(i.at)} · read by {i.interpretedBy}
            </figcaption>
            <blockquote className="mt-1 whitespace-pre-wrap border-l-4 py-1 pl-3">{i.text}</blockquote>
          </figure>
        ))}
      </CardContent>
    </Card>
  );
}
