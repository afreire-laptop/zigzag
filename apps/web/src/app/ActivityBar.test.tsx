import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ActivityBar } from "./ActivityBar";

it("shows progress with elapsed time and cancel, then a focused failure with its actions", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  let clock = 0;
  const handlers = { onCancel: vi.fn(), onReload: vi.fn(), onDismiss: vi.fn() };
  const { rerender } = render(
    <ActivityBar
      busy={{ label: "Reading your brief…", operationId: "op1", startedAt: 0 }}
      notice={null}
      problem={null}
      now={() => clock}
      {...handlers}
    />,
  );
  expect(screen.getByRole("status")).toHaveTextContent("Reading your brief…");
  clock = 3000;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(screen.getByRole("status")).toHaveTextContent("3s");
  vi.useRealTimers();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(handlers.onCancel).toHaveBeenCalled();

  const retry = vi.fn();
  rerender(
    <ActivityBar
      busy={null}
      notice={null}
      problem={{ message: "It failed.", issues: ["Not JSON."], retry, reload: true }}
      now={() => clock}
      {...handlers}
    />,
  );
  const alert = screen.getByRole("alert");
  expect(alert).toHaveFocus();
  expect(alert).toHaveTextContent("Not JSON.");
  await user.click(screen.getByRole("button", { name: "Retry" }));
  await user.click(screen.getByRole("button", { name: "Reload saved state" }));
  await user.click(screen.getByRole("button", { name: "Dismiss" }));
  expect(retry).toHaveBeenCalled();
  expect(handlers.onReload).toHaveBeenCalled();
  expect(handlers.onDismiss).toHaveBeenCalled();

  rerender(<ActivityBar busy={null} notice="Saved." problem={null} now={() => clock} {...handlers} />);
  expect(screen.getByRole("status")).toHaveTextContent("Saved.");
});
