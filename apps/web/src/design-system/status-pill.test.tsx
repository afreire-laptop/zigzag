import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { StatusPill } from "./status-pill";

it("labels drafts and reviewed revisions", () => {
  const { rerender } = render(<StatusPill reviewed={false} revision={3} />);
  expect(screen.getByText("Draft · revision 3")).toBeInTheDocument();
  rerender(<StatusPill reviewed revision={3} />);
  expect(screen.getByText("Reviewed · revision 3")).toBeInTheDocument();
});
