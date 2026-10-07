import type { ProjectView, QuestionView, StatusView } from "@intent-harness/api-client";
import { type RefObject, useState } from "react";
import { plural } from "@/design-system/lib/format";
import { Button } from "@/design-system/ui/button";
import { Card, CardContent, CardHeader } from "@/design-system/ui/card";
import { DecisionPanel } from "@/features/decision/DecisionPanel";
import type { Workspace } from "@/features/workspace/use-workspace";
import { History, Sources } from "./History";
import { OpenItems } from "./OpenItems";
import { ReplyBox } from "./ReplyBox";
import { Understanding } from "./Understanding";

/** A question can be brought into the decision panel when the API permits any action on it. */
const actionable = (q: QuestionView | undefined): q is QuestionView =>
  q !== undefined && (q.actions.select || q.actions.answerInOwnWords || q.actions.leaveOpen);

export function WorkingBrief(props: {
  project: ProjectView;
  status: StatusView | null;
  busy: boolean;
  workspace: Pick<Workspace, "decide" | "reply">;
  headingRef: RefObject<HTMLHeadingElement | null>;
  onReview: () => void;
}) {
  const { project, busy, workspace } = props;
  const [chosen, setChosen] = useState<{ id: string; revision: number } | null>(null);
  const picked = chosen?.revision === project.revision ? project.questions.find((q) => q.id === chosen.id) : undefined;
  const focus = project.questions.find((q) => q.id === project.focusId);
  const active = actionable(picked) ? picked : focus?.status === "open" ? focus : undefined;
  const fixtureReplies = props.status?.fixtures?.replies ?? null;

  const pick = (id: string) => {
    setChosen({ id, revision: project.revision });
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? true;
    requestAnimationFrame(() => {
      document.getElementById("decision")?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
      props.headingRef.current?.focus({ preventScroll: true });
    });
  };

  return (
    <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_400px]">
      <div className="grid gap-5">
        <Understanding intent={project.intent} busy={busy} decide={workspace.decide} />
        <OpenItems
          project={project}
          busy={busy}
          activeId={active?.id ?? null}
          onPick={pick}
          decide={workspace.decide}
        />
        <History decisions={project.decisions} />
        <Sources inputs={project.inputs} />
      </div>
      <aside className="grid gap-5" aria-label="Decision and replies">
        {active ? (
          <DecisionPanel
            key={`${active.id}:${project.revision}`}
            question={active}
            isFocus={active.id === project.focusId}
            busy={busy}
            decide={workspace.decide}
            reply={workspace.reply}
            fixtureReplies={fixtureReplies}
            headingRef={props.headingRef}
          />
        ) : (
          <NothingToAsk project={project} headingRef={props.headingRef} onReview={props.onReview} />
        )}
        <ReplyBox busy={busy} reply={workspace.reply} fixtureReplies={fixtureReplies} />
      </aside>
    </div>
  );
}

function NothingToAsk(props: {
  project: ProjectView;
  headingRef: RefObject<HTMLHeadingElement | null>;
  onReview: () => void;
}) {
  const open = props.project.openQuestionCount;
  return (
    <Card className="border-primary ring-1 ring-primary" id="decision" aria-labelledby="nothing-heading">
      <CardHeader>
        <h2 id="nothing-heading" ref={props.headingRef} tabIndex={-1} className="text-xl font-semibold outline-none">
          Nothing needs your answer now
        </h2>
      </CardHeader>
      <CardContent className="space-y-3">
        <p>
          {open === 0
            ? "No questions are open."
            : `${open} ${plural(open, "question remains", "questions remain")} open and will be listed in the handoff as unresolved.`}{" "}
          When the understanding looks right, review the handoff.
        </p>
        <Button onClick={props.onReview}>Review the handoff</Button>
      </CardContent>
    </Card>
  );
}
