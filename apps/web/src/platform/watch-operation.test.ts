import { describe, expect, it, vi } from "vitest";
import { operation } from "@/test/factories";
import { streams } from "@/test/streams";
import { isTerminal, watchOperation } from "./watch-operation";

const eventsUrl = (id: string) => `/api/operations/${id}/events`;

describe("watchOperation", () => {
  it("applies each persisted state once and resolves at the terminal state", async () => {
    const s = streams();
    const seen: number[] = [];
    const done = watchOperation(
      "op1",
      (op) => seen.push(op.version),
      { openStream: s.openStream, fetchOperation: vi.fn(), eventsUrl },
      new AbortController().signal,
    );
    const stream = s.latest();
    expect(stream.url).toBe("/api/operations/op1/events");
    stream.emit(operation({ version: 1 }));
    stream.emit(operation({ version: 1 })); // repeated notification
    stream.emit("not json");
    stream.emit({ unexpected: true }); // fails the generated schema
    stream.emit(operation({ version: 2, status: "running" }));
    stream.emit(operation({ version: 3, status: "succeeded" }));
    await expect(done).resolves.toMatchObject({ status: "succeeded" });
    expect(seen).toEqual([1, 2, 3]);
    expect(stream.closed).toBe(true);
  });

  it("asks the REST resource when the stream drops, and reopens while work continues", async () => {
    vi.useFakeTimers();
    const s = streams();
    const fetchOperation = vi
      .fn()
      .mockResolvedValueOnce(operation({ version: 2, status: "running" }))
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(operation({ version: 4, status: "failed" }));
    const done = watchOperation(
      "op1",
      () => undefined,
      { openStream: s.openStream, fetchOperation, eventsUrl, retryDelayMs: 10 },
      new AbortController().signal,
    );
    s.latest().fail();
    await vi.advanceTimersByTimeAsync(10);
    expect(s.opened).toHaveLength(2);
    s.latest().fail();
    await vi.advanceTimersByTimeAsync(10);
    expect(s.opened).toHaveLength(3);
    s.latest().fail();
    await expect(done).resolves.toMatchObject({ status: "failed", version: 4 });
    vi.useRealTimers();
  });

  it("stops and rejects when aborted", async () => {
    const s = streams();
    const controller = new AbortController();
    const done = watchOperation(
      "op1",
      () => undefined,
      { openStream: s.openStream, fetchOperation: vi.fn(), eventsUrl },
      controller.signal,
    );
    controller.abort(new Error("left the page"));
    await expect(done).rejects.toThrow("left the page");
    expect(s.latest().closed).toBe(true);
  });

  it("knows the terminal states", () => {
    expect(
      ["succeeded", "failed", "cancelled", "interrupted"].every((status) =>
        isTerminal(operation({ status: status as never })),
      ),
    ).toBe(true);
    expect(isTerminal(operation({ status: "running" }))).toBe(false);
  });
});
