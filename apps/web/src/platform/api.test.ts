import { client } from "@zigzag/api-client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { operation, project } from "@/test/factories";
import { api, RequestFailed, toFailure } from "./api";

function respond(status: number, body: unknown, type = "application/json") {
  const fetch = vi.fn<typeof globalThis.fetch>(
    async () => new Response(JSON.stringify(body), { status, headers: { "content-type": type } }),
  );
  client.setConfig({ baseUrl: "http://api.test", fetch });
  return fetch;
}

function sent(fetch: ReturnType<typeof respond>): Request {
  const request = fetch.mock.calls.at(-1)?.[0];
  if (!(request instanceof Request)) throw new Error("The SDK did not send a Request.");
  return request;
}

afterEach(() => client.setConfig({ baseUrl: "", fetch: globalThis.fetch }));

const problem = {
  type: "/problems/conflict",
  title: "Conflict",
  status: 409,
  detail: "This page shows revision 1, but revision 2 is saved. Reload to continue.",
  kind: "conflict",
  retryable: false,
  issues: [],
  activeOperationId: null,
};

describe("api", () => {
  it("returns validated data from the generated SDK", async () => {
    const fetch = respond(202, operation());
    await expect(api.create("A brief.")).resolves.toMatchObject({ id: "op1", status: "queued" });
    const request = sent(fetch);
    expect(request.url).toBe("http://api.test/api/projects");
    expect(await request.json()).toEqual({ brief: "A brief." });
  });

  it("sends the revision a command is based on", async () => {
    const p = project({ revision: 4 });
    const fetch = respond(200, p);
    await api.decide(p, { type: "rely", itemId: "a1" });
    expect(await sent(fetch).json()).toEqual({ type: "rely", itemId: "a1", baseRevision: 4 });
  });

  it("turns a problem response into a typed failure", async () => {
    respond(409, problem, "application/problem+json");
    const failure = await api.review(project()).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(RequestFailed);
    expect((failure as RequestFailed).failure).toEqual({
      message: problem.detail,
      kind: "conflict",
      retryable: false,
      issues: [],
      activeOperationId: null,
    });
  });

  it("reports an unreachable server as retryable", async () => {
    client.setConfig({
      baseUrl: "http://api.test",
      fetch: vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))),
    });
    const failure = await api.status().catch((e: unknown) => e);
    expect((failure as RequestFailed).failure).toMatchObject({ kind: "network", retryable: true });
  });

  it("builds same-origin URLs for downloads and events", () => {
    expect(api.exportUrl("p1", "markdown")).toBe("/api/projects/p1/exports/markdown");
    expect(api.exportUrl("p1", "json", 3)).toBe("/api/projects/p1/exports/json?revision=3");
    expect(api.eventsUrl("op1")).toBe("/api/operations/op1/events");
  });

  it("describes unreadable failures", () => {
    expect(toFailure({ nope: true }, 502)).toMatchObject({ message: "The server answered 502.", kind: "server" });
    expect(toFailure(undefined)).toMatchObject({ message: "The server's response could not be read." });
  });
});
