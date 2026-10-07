import type { RecoveryView, StatusView } from "@intent-harness/api-client";
import { type FormEvent, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/design-system/ui/alert";
import { Button } from "@/design-system/ui/button";
import { Label } from "@/design-system/ui/label";
import { Textarea } from "@/design-system/ui/textarea";
import { FixturePicker } from "./FixturePicker";

export function Intake(props: {
  status: StatusView | null;
  recovery: RecoveryView | null;
  busy: boolean;
  onSubmit: (text: string) => Promise<boolean>;
  onCancel?: () => void;
}) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!text.trim()) {
      setError("Paste or write a brief first.");
      return;
    }
    setError(null);
    await props.onSubmit(text.trim());
  }

  return (
    <section className="mx-auto mt-10 max-w-3xl" aria-labelledby="intake-heading">
      <h1 id="intake-heading" className="text-2xl font-semibold tracking-tight">
        Start from a brief
      </h1>
      <p className="mt-2 max-w-2xl text-muted-foreground">
        Paste an idea or brief as you would give it to a colleague. Intent Harness records what you said in your own
        words, points out the few uncertainties that would change the next step, and lets you choose or leave them open.
      </p>
      {props.recovery && (
        <Alert className="mt-4 border-warning-foreground/40 bg-warning text-warning-foreground">
          <AlertTitle>The most recent saved project could not be opened.</AlertTitle>
          <AlertDescription className="text-warning-foreground">
            <p>
              <code className="break-all">{props.recovery.file}</code> ({props.recovery.reason}). It was left untouched,
              and no older project is shown in its place.
            </p>
            <p className="mt-1">
              Restore the file from a backup or move it out of the data directory, then reload. You can also start a new
              brief below.
            </p>
          </AlertDescription>
        </Alert>
      )}
      <form onSubmit={submit} noValidate className="mt-6 space-y-2">
        <Label htmlFor="brief">Brief</Label>
        <Textarea
          id="brief"
          rows={9}
          value={text}
          onChange={(e) => setText(e.target.value)}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? "brief-error brief-hint" : "brief-hint"}
          disabled={props.busy}
        />
        <p id="brief-hint" className="text-sm text-muted-foreground">
          Include whatever you already know: who it is for, what is out of scope, what the next step should be. Leave
          out what you do not know.
        </p>
        {error && (
          <p id="brief-error" className="text-sm font-semibold text-destructive">
            {error}
          </p>
        )}
        {props.status?.fixtures && (
          <FixturePicker texts={props.status.fixtures.briefs} onPick={setText} busy={props.busy} />
        )}
        <div className="flex flex-wrap gap-2 pt-2">
          <Button type="submit" disabled={props.busy}>
            Read brief
          </Button>
          {props.onCancel && (
            <Button type="button" variant="ghost" onClick={props.onCancel} disabled={props.busy}>
              Back to current brief
            </Button>
          )}
        </div>
      </form>
    </section>
  );
}
