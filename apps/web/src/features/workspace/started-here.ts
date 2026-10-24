/**
 * The operations this tab started, kept in sessionStorage so they survive a reload of the tab but are never
 * shared with other windows. After a reload, the workspace resumes following only its own work and work on
 * the brief it shows, so another window's operation cannot replace that brief. Storage failures only mean a
 * reload will not resume following.
 */
const KEY = "zigzag:started-operations";
const KEEP = 20;

function read(): string[] {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(KEY) ?? "[]");
    return Array.isArray(value) ? value.filter((id): id is string => typeof id === "string") : [];
  } catch {
    return [];
  }
}

function write(ids: string[]): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(ids.slice(-KEEP)));
  } catch {
    // Storage unavailable: nothing to resume after a reload.
  }
}

export const startedHere = {
  add: (id: string) => write([...read().filter((x) => x !== id), id]),
  remove: (id: string) => write(read().filter((x) => x !== id)),
  has: (id: string) => read().includes(id),
};
