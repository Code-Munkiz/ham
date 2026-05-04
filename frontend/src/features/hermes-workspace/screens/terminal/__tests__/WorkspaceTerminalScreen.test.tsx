/**
 * PR-1: friendly empty state on `/workspace/terminal` when no runtime is
 * connected and developer mode is off. No `uvicorn` or "local API" copy
 * should appear in the normal hosted state.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../WorkspaceTerminalView", () => ({
  WorkspaceTerminalView: () => <div data-testid="hww-terminal-view-mock" />,
}));

vi.mock("../../../components/LocalMachineConnectCta", () => ({
  LocalMachineConnectCta: () => <div data-testid="hww-local-connect-cta-mock" />,
}));

import { WorkspaceTerminalScreen } from "../WorkspaceTerminalScreen";

function renderScreen() {
  return render(
    <MemoryRouter>
      <WorkspaceTerminalScreen />
    </MemoryRouter>,
  );
}

describe("WorkspaceTerminalScreen empty state (PR-1)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    localStorage.clear();
  });

  it("shows a friendly empty state without uvicorn / local API copy when no runtime is connected", () => {
    renderScreen();

    expect(screen.getByRole("heading", { name: /terminal/i })).toBeInTheDocument();
    expect(
      screen.getByText("Terminal requires a connected runtime."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Connect HAM Desktop or enable developer mode to use terminal features."),
    ).toBeInTheDocument();

    const html = document.body.innerHTML;
    expect(html).not.toMatch(/uvicorn/i);
    expect(html).not.toMatch(/local API/i);
    expect(html).not.toMatch(/127\.0\.0\.1/);

    expect(screen.queryByTestId("hww-local-connect-cta-mock")).toBeNull();
    expect(screen.queryByTestId("hww-terminal-view-mock")).toBeNull();
  });

  it("shows the local-machine connect CTA in the empty state when developer mode is enabled", () => {
    vi.stubEnv("VITE_HAM_SHOW_LOCAL_DEV_HINTS", "true");

    renderScreen();

    expect(screen.getByTestId("hww-local-connect-cta-mock")).toBeInTheDocument();
  });

  it("renders the terminal view when a local runtime is configured", () => {
    localStorage.setItem("hww.localRuntimeBase", "http://127.0.0.1:8001");

    renderScreen();

    expect(screen.getByTestId("hww-terminal-view-mock")).toBeInTheDocument();
  });
});
