import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { Markdown } from "./Markdown";

it("renders the handoff subset of Markdown as elements, never raw HTML", () => {
  const source = [
    "# Intent handoff: Title",
    "",
    "**Status: DRAFT.**",
    "",
    "## Desired outcome",
    "",
    "- First item  ",
    "  _From your brief_",
    "- Second <b>item</b>",
    "",
    "### Brief s1",
    "",
    "> Quoted line one",
    "> Quoted line two",
    "",
    "---",
    "",
    "_footer_",
  ].join("\n");
  const { container } = render(<Markdown source={source} />);
  expect(screen.getByRole("heading", { level: 3, name: "Intent handoff: Title" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 4, name: "Desired outcome" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 5, name: "Brief s1" })).toBeInTheDocument();
  expect(screen.getByText("Status: DRAFT.").tagName).toBe("STRONG");
  expect(screen.getByText("From your brief").tagName).toBe("EM");
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
  expect(screen.getByText("Second <b>item</b>")).toBeInTheDocument();
  expect(container.querySelector("b")).toBeNull();
  expect(container.querySelector("blockquote")?.textContent).toBe("Quoted line one\nQuoted line two");
  expect(container.querySelector("hr")).not.toBeNull();
  expect(container.querySelectorAll("br")).toHaveLength(1);
});
