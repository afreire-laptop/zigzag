// Follows one operation to its end. SSE only says "something changed"; each message carries the persisted
// state, is validated, and is applied once per version. If the stream drops, the REST resource is asked
// directly, and the stream is reopened if work is still in progress. Nothing here starts or repeats work.
import { type Operation, zOperation } from "@intent-harness/api-client";

export type StreamLike = {
  onmessage: ((event: MessageEvent<string>) => void) | null;
  onerror: ((event: Event) => void) | null;
  close(): void;
};

export type WatchDeps = {
  openStream: (url: string) => StreamLike;
  fetchOperation: (operationId: string) => Promise<Operation>;
  eventsUrl: (operationId: string) => string;
  retryDelayMs?: number;
};

const TERMINAL = new Set<Operation["status"]>(["succeeded", "failed", "cancelled", "interrupted"]);
export const isTerminal = (op: Operation): boolean => TERMINAL.has(op.status);

export function watchOperation(
  operationId: string,
  onUpdate: (op: Operation) => void,
  deps: WatchDeps,
  signal: AbortSignal,
): Promise<Operation> {
  return new Promise<Operation>((resolve, reject) => {
    let lastVersion = 0;
    let stream: StreamLike | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const stop = () => {
      stream?.close();
      stream = null;
      clearTimeout(timer);
    };
    const accept = (op: Operation) => {
      if (op.version <= lastVersion) return; // a repeated or older notification
      lastVersion = op.version;
      onUpdate(op);
      if (isTerminal(op)) {
        stop();
        resolve(op);
      }
    };
    const open = () => {
      if (signal.aborted) return;
      stream = deps.openStream(deps.eventsUrl(operationId));
      stream.onmessage = (event) => {
        let data: unknown;
        try {
          data = JSON.parse(event.data);
        } catch {
          return;
        }
        const parsed = zOperation.safeParse(data);
        if (parsed.success) accept(parsed.data);
      };
      stream.onerror = () => {
        stop();
        deps.fetchOperation(operationId).then(
          (op) => {
            accept(op);
            if (!isTerminal(op)) timer = setTimeout(open, deps.retryDelayMs ?? 1000);
          },
          () => {
            timer = setTimeout(open, deps.retryDelayMs ?? 1000);
          },
        );
      };
    };

    signal.addEventListener(
      "abort",
      () => {
        stop();
        reject(signal.reason);
      },
      { once: true },
    );
    open();
  });
}
