// The draft/reviewed label used on both surfaces. Project code, not shadcn output.
import { cn } from "cn";

export function StatusPill({ reviewed, revision }: { reviewed: boolean; revision: number }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-3 py-1 text-sm font-semibold",
        reviewed ? "bg-reviewed text-reviewed-foreground" : "bg-draft text-draft-foreground",
      )}
    >
      {reviewed ? `Reviewed · revision ${revision}` : `Draft · revision ${revision}`}
    </span>
  );
}
