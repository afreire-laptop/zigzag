import { Button } from "@/design-system/ui/button";

/** Fixture mode only: insert a journey text that has a canned response. */
export function FixturePicker(props: {
  texts: readonly { label: string; text: string }[];
  onPick: (text: string) => void;
  busy: boolean;
}) {
  return (
    <div className="my-2 flex flex-wrap items-center gap-2 text-sm text-warning-foreground">
      <span>Fixture texts:</span>
      {props.texts.map((t) => (
        <Button
          key={t.label}
          type="button"
          variant="outline"
          size="sm"
          className="border-warning-foreground/40 text-warning-foreground"
          onClick={() => props.onPick(t.text)}
          disabled={props.busy}
        >
          {t.label}
        </Button>
      ))}
    </div>
  );
}
