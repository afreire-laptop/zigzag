import type { StreamLike } from "@/platform/watch-operation";

/** A controllable stand-in for EventSource. */
export class FakeStream implements StreamLike {
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  closed = false;

  constructor(readonly url: string) {}

  emit(data: unknown): void {
    this.onmessage?.(new MessageEvent("message", { data: typeof data === "string" ? data : JSON.stringify(data) }));
  }

  fail(): void {
    this.onerror?.(new Event("error"));
  }

  close(): void {
    this.closed = true;
  }
}

export function streams() {
  const opened: FakeStream[] = [];
  return {
    opened,
    openStream: (url: string) => {
      const s = new FakeStream(url);
      opened.push(s);
      return s;
    },
    latest: (): FakeStream => {
      const s = opened.at(-1);
      if (!s) throw new Error("No stream opened yet.");
      return s;
    },
  };
}
