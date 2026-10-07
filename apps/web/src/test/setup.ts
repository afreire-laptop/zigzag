import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom has no ResizeObserver; Radix primitives measure elements with it.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver ??= ResizeObserverStub;
// jsdom does not lay out pages, so it has no scrolling.
Element.prototype.scrollIntoView ??= () => undefined;

afterEach(() => {
  cleanup();
});
