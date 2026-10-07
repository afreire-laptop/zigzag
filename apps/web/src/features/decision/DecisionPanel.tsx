import type { QuestionView } from "@intent-harness/api-client";
import { type FormEvent, type Ref, useId, useState } from "react";
import { Button } from "@/design-system/ui/button";
import { Card, CardContent, CardHeader } from "@/design-system/ui/card";
import { Input } from "@/design-system/ui/input";
import { Label } from "@/design-system/ui/label";
import { RadioGroup, RadioGroupItem } from "@/design-system/ui/radio-group";
import { Textarea } from "@/design-system/ui/textarea";
import { FixturePicker } from "@/features/intake/FixturePicker";
import type { Workspace } from "@/features/workspace/use-workspace";

const WRITE = "write";

function eyebrow(q: QuestionView, isFocus: boolean): string {
  if (q.status === "answered") return "Change your answer";
  if (q.status === "deferred") return "You left this open";
  return isFocus ? "Needs your decision" : "Open question";
}

/** One focused decision: proposed options, the user's own words, or leaving it open. Every permitted action
 * comes from the question's `actions`, which the API derives from the same rules it enforces. */
export function DecisionPanel(props: {
  question: QuestionView;
  isFocus: boolean;
  busy: boolean;
  decide: Workspace["decide"];
  reply: Workspace["reply"];
  fixtureReplies: readonly { label: string; text: string }[] | null;
  headingRef: Ref<HTMLHeadingElement>;
}) {
  const { question: q, busy } = props;
  const actions = q.actions;
  const ids = { heading: useId(), answer: useId(), note: useId(), error: useId(), legend: useId() };
  const selectable = actions.select ? q.options : [];
  const [choice, setChoice] = useState<string | null>(
    selectable.length === 0 && actions.answerInOwnWords ? WRITE : null,
  );
  const [answer, setAnswer] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const writing = choice === WRITE;
  const current = q.resolution;
  const canSubmit = selectable.length > 0 || actions.answerInOwnWords;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!choice) return setError("Choose a direction, write your own answer, or leave the question open.");
    if (writing && !answer.trim()) return setError("Write your answer first.");
    setError(null);
    if (writing) await props.reply(answer.trim(), q.id);
    else
      await props.decide(
        { type: "select", questionId: q.id, optionId: choice, reason: note.trim() || null },
        "Recording your choice…",
        "reassess",
      );
  }

  const leaveOpen = () =>
    void props.decide(
      { type: "defer", questionId: q.id, reason: note.trim() || null },
      q.status === "answered" ? "Withdrawing the answer and leaving it open…" : "Recording that this stays open…",
      "reassess",
    );

  return (
    <Card className="border-primary ring-1 ring-primary" id="decision" aria-labelledby={ids.heading}>
      <CardHeader>
        <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">{eyebrow(q, props.isFocus)}</p>
        <h2 id={ids.heading} ref={props.headingRef} tabIndex={-1} className="text-xl font-semibold outline-none">
          {q.text}
        </h2>
        <dl className="mt-2 space-y-1 text-sm">
          <dt className="font-semibold">What it changes</dt>
          <dd className="text-muted-foreground">{q.effect}</dd>
          <dt className="font-semibold">Basis</dt>
          <dd className="text-muted-foreground">
            {q.basis}
            {q.sourceQuote && <> Your words: “{q.sourceQuote}”</>}
          </dd>
        </dl>
        {current && (
          <p className="mt-2 rounded-md bg-muted px-3 py-2 text-sm">
            {current.via === "leftOpen" ? "Left open: " : "Current answer: "}
            {current.summary}
          </p>
        )}
        {current?.via === "ownWords" && (
          <p className="mt-2 text-sm text-muted-foreground">
            You answered this in your own words. Correct or remove those statements under Current understanding, or
            leave the question open again.
          </p>
        )}
      </CardHeader>
      <CardContent>
        {canSubmit && (
          <form onSubmit={submit} noValidate>
            <fieldset disabled={busy} className="min-w-0 space-y-3" aria-describedby={error ? ids.error : undefined}>
              <legend id={ids.legend} className="mb-2 text-sm font-semibold">
                {selectable.length > 0
                  ? "Proposed directions. None is selected until you choose."
                  : "Answer in your own words"}
              </legend>
              {(selectable.length > 0 || (actions.answerInOwnWords && q.options.length > 0)) && (
                <RadioGroup
                  value={choice ?? ""}
                  onValueChange={setChoice}
                  aria-labelledby={ids.legend}
                  className="gap-2"
                >
                  {selectable.map((o) => {
                    const isCurrent = current?.via === "option" && current.optionId === o.id;
                    const id = `${ids.legend}-${o.id}`;
                    return (
                      <div
                        key={o.id}
                        className="flex gap-3 rounded-lg border p-3 has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-muted"
                      >
                        <RadioGroupItem value={o.id} id={id} disabled={isCurrent} className="mt-1" />
                        <Label htmlFor={id} className="grid gap-1 font-normal leading-snug">
                          <span className="font-semibold">
                            {o.label}
                            {isCurrent && " (current answer)"}
                          </span>
                          <span>{o.description}</span>
                          <span className="text-muted-foreground">
                            <strong>Trade-off:</strong> {o.tradeoff}
                          </span>
                          <span className="text-muted-foreground">
                            <strong>Would record:</strong>{" "}
                            {o.establishes.map((s) => `${s.label}: ${s.text}`).join(" · ")}
                          </span>
                        </Label>
                      </div>
                    );
                  })}
                  {actions.answerInOwnWords && q.options.length > 0 && (
                    <div className="flex gap-3 rounded-lg border p-3 has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-muted">
                      <RadioGroupItem value={WRITE} id={`${ids.legend}-write`} className="mt-1" />
                      <Label htmlFor={`${ids.legend}-write`} className="grid gap-1 font-normal leading-snug">
                        <span className="font-semibold">Something else</span>
                        <span>Write a different direction, or correct the question's premise.</span>
                      </Label>
                    </div>
                  )}
                </RadioGroup>
              )}

              {writing ? (
                <div className="space-y-1">
                  <Label htmlFor={ids.answer}>Your answer</Label>
                  <Textarea id={ids.answer} rows={4} value={answer} onChange={(e) => setAnswer(e.target.value)} />
                  <p className="text-sm text-muted-foreground">
                    A short answer is fine. You can also volunteer other choices; each is recorded with your wording.
                  </p>
                  {props.fixtureReplies && (
                    <FixturePicker texts={props.fixtureReplies} onPick={setAnswer} busy={busy} />
                  )}
                </div>
              ) : (
                <div className="space-y-1">
                  <Label htmlFor={ids.note}>Reason (optional)</Label>
                  <Input id={ids.note} value={note} onChange={(e) => setNote(e.target.value)} />
                </div>
              )}
            </fieldset>
            {error && (
              <p id={ids.error} role="alert" className="mt-2 text-sm font-semibold text-destructive">
                {error}
              </p>
            )}
            <Button type="submit" className="mt-3" disabled={busy}>
              {writing ? "Send answer" : "Record choice"}
            </Button>
          </form>
        )}

        {actions.leaveOpen && (
          <div className="mt-4 border-t border-dashed pt-4">
            <Button type="button" variant="outline" onClick={leaveOpen} disabled={busy}>
              {q.status === "answered" ? "Withdraw answer and leave open" : "Leave this open"}
            </Button>
            <p className="mt-2 text-sm text-muted-foreground">
              {q.status === "answered"
                ? "The question returns to the handoff as unresolved. A selected option's statements are removed; the earlier decision stays in the history as superseded."
                : (q.deferEffect ?? "The question stays open and is listed in the handoff as unresolved.")}
            </p>
          </div>
        )}
        <p className="mt-4 text-xs text-muted-foreground">Question and options proposed by {q.proposedBy}.</p>
      </CardContent>
    </Card>
  );
}
