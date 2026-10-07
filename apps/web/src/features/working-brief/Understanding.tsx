import type { IntentSectionView, StatementView } from "@intent-harness/api-client";
import { type FormEvent, useId, useState } from "react";
import { Button } from "@/design-system/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/design-system/ui/card";
import { Label } from "@/design-system/ui/label";
import { Textarea } from "@/design-system/ui/textarea";
import type { Workspace } from "@/features/workspace/use-workspace";

export function Understanding(props: {
  intent: readonly IntentSectionView[];
  busy: boolean;
  decide: Workspace["decide"];
}) {
  return (
    <Card aria-labelledby="understanding-heading">
      <CardHeader>
        <CardTitle>
          <h2 id="understanding-heading">Current understanding</h2>
        </CardTitle>
        <CardDescription>
          Recorded from your words or from options you chose. Each statement shows where it came from. Correct anything
          that misreads you.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <dl>
          {props.intent.map((section) => (
            <div
              key={section.kind}
              className="grid gap-1 border-t py-3 sm:grid-cols-[11rem_minmax(0,1fr)] sm:gap-4"
              data-section={section.kind}
            >
              <dt className="text-sm font-bold">{section.label}</dt>
              <dd>
                {section.items.length === 0 ? (
                  <span className="italic text-muted-foreground">Not established</span>
                ) : (
                  <ul className="space-y-3">
                    {section.items.map((item) => (
                      <Statement key={`${item.id}:${item.text}`} item={item} busy={props.busy} decide={props.decide} />
                    ))}
                  </ul>
                )}
              </dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}

function Statement({ item, busy, decide }: { item: StatementView; busy: boolean; decide: Workspace["decide"] }) {
  const [mode, setMode] = useState<"view" | "edit" | "remove">("view");
  const [draft, setDraft] = useState(item.text);
  const fieldId = useId();

  async function save(event: FormEvent) {
    event.preventDefault();
    if (await decide({ type: "edit", itemId: item.id, text: draft }, "Saving your correction…")) setMode("view");
  }

  if (mode === "edit") {
    return (
      <li>
        <form onSubmit={save} className="space-y-2">
          <Label htmlFor={fieldId}>Correct this statement</Label>
          <Textarea
            id={fieldId}
            rows={2}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            disabled={busy}
            autoFocus
          />
          <p className="text-sm text-muted-foreground">{item.basis}</p>
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={busy || !draft.trim() || draft.trim() === item.text}>
              Save correction
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => {
                setDraft(item.text);
                setMode("view");
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      </li>
    );
  }

  return (
    <li>
      <p className="text-[1.02rem]">{item.text}</p>
      <p className="text-sm text-muted-foreground">{item.basis}</p>
      {mode === "remove" ? (
        <fieldset className="mt-1 flex flex-wrap items-center gap-2 text-sm">
          <legend className="sr-only">Confirm removing: {item.text}</legend>
          <span>Remove this statement? The decision history keeps its wording.</span>
          <Button
            size="sm"
            variant="destructive"
            onClick={() => void decide({ type: "remove", itemId: item.id }, "Removing the statement…")}
            disabled={busy}
          >
            Remove
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setMode("view")}>
            Keep
          </Button>
        </fieldset>
      ) : (
        <div className="flex gap-3">
          <Button
            variant="link"
            size="sm"
            className="h-auto px-0"
            onClick={() => setMode("edit")}
            disabled={busy}
            aria-label={`Correct: ${item.text}`}
          >
            Correct
          </Button>
          <Button
            variant="link"
            size="sm"
            className="h-auto px-0"
            onClick={() => setMode("remove")}
            disabled={busy}
            aria-label={`Remove: ${item.text}`}
          >
            Remove
          </Button>
        </div>
      )}
    </li>
  );
}
