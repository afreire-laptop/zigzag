import { type FormEvent, useState } from "react";
import { Button } from "@/design-system/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/design-system/ui/card";
import { Label } from "@/design-system/ui/label";
import { Textarea } from "@/design-system/ui/textarea";
import { FixturePicker } from "@/features/intake/FixturePicker";
import type { Workspace } from "@/features/workspace/use-workspace";

export function ReplyBox(props: {
  busy: boolean;
  reply: Workspace["reply"];
  fixtureReplies: readonly { label: string; text: string }[] | null;
}) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!text.trim()) return setError("Write an instruction or correction first.");
    setError(null);
    if (await props.reply(text.trim(), null)) setText("");
  }

  return (
    <Card aria-labelledby="reply-heading">
      <CardHeader>
        <CardTitle>
          <h2 id="reply-heading">Add an instruction or correction</h2>
        </CardTitle>
        <CardDescription>
          Explicit instructions are recorded as your choices, with your wording kept as the source. Anything the model
          infers stays a proposal.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} noValidate className="space-y-2">
          <Label htmlFor="reply" className="sr-only">
            Instruction or correction
          </Label>
          <Textarea
            id="reply"
            rows={4}
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={props.busy}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? "reply-error" : undefined}
          />
          {error && (
            <p id="reply-error" className="text-sm font-semibold text-destructive">
              {error}
            </p>
          )}
          {props.fixtureReplies && <FixturePicker texts={props.fixtureReplies} onPick={setText} busy={props.busy} />}
          <Button type="submit" variant="outline" disabled={props.busy}>
            Send
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
