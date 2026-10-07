import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fakeApi, handoff, project } from "@/test/factories";
import { ReviewSurface } from "./ReviewSurface";

describe("ReviewSurface", () => {
  it("shows a draft with its changes since the last review and offers review once the document is current", async () => {
    const api = fakeApi();
    api.handoff.mockResolvedValue(
      handoff({
        current: {
          revision: 2,
          status: "draft",
          markdown: "# Intent handoff: T\n\n**Status: DRAFT. Revision 2**\n",
          json: "{}",
        },
        lastReviewed: { revision: 1, reviewedAt: "2026-10-06T10:00:00.000Z" },
        reviews: [{ revision: 1, reviewedAt: "2026-10-06T10:00:00.000Z" }],
        changes: [{ section: "Desired outcome", added: ["New text."], removed: ["Old text."] }],
      }),
    );
    const onReview = vi.fn(async () => true);
    render(
      <ReviewSurface
        project={project({ revision: 2, openQuestionCount: 2 })}
        busy={false}
        api={api}
        onReview={onReview}
      />,
    );
    const button = screen.getByRole("button", { name: "Mark revision 2 reviewed" });
    expect(button).toBeDisabled();
    await waitFor(() => expect(button).toBeEnabled());
    expect(screen.getByText(/The last reviewed revision is 1/)).toBeInTheDocument();
    expect(screen.getByText(/2 questions remain open/)).toBeInTheDocument();
    expect(screen.getByText("No next step is established.")).toBeInTheDocument();
    expect(screen.getByText("Changed since reviewed revision 1")).toBeInTheDocument();
    expect(screen.getByText("Old text.").closest("li")).toHaveTextContent("Removed: Old text.");
    expect(screen.getByText("New text.").closest("li")).toHaveTextContent("Added: New text.");
    expect(screen.getByRole("link", { name: "Download Markdown (draft)" })).toHaveAttribute(
      "href",
      "/api/projects/p1/exports/markdown",
    );
    expect(screen.getByRole("link", { name: "JSON, revision 1" })).toHaveAttribute(
      "href",
      "/api/projects/p1/exports/json?revision=1",
    );
    await userEvent.setup().click(button);
    expect(onReview).toHaveBeenCalled();
  });

  it("shows a reviewed revision without a review button", async () => {
    const api = fakeApi();
    api.handoff.mockResolvedValue(
      handoff({ current: { revision: 1, status: "reviewed", markdown: "Reviewed. Revision 1", json: "{}" } }),
    );
    render(
      <ReviewSurface
        project={project({ status: "reviewed", hasNextStep: true, openQuestionCount: 1 })}
        busy={false}
        api={api}
        onReview={vi.fn()}
      />,
    );
    expect(screen.getByText(/Revision 1 is reviewed/)).toBeInTheDocument();
    expect(screen.getByText(/1 question remains open/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Mark revision/ })).toBeNull();
    expect(screen.getByRole("link", { name: "Download JSON" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("handoff")).toHaveTextContent("Reviewed. Revision 1"));
  });

  it("reports a handoff that cannot be loaded", async () => {
    const api = fakeApi();
    api.handoff.mockRejectedValue(new Error("Server down."));
    render(<ReviewSurface project={project({ openQuestionCount: 0 })} busy={false} api={api} onReview={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load the handoff: Server down.");
  });
});
