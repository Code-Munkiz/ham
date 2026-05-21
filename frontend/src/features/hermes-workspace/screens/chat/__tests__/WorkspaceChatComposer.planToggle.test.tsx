/** Plan toggle in WorkspaceChatComposer. */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../WorkspaceVoiceMessageInput", () => ({
  WorkspaceVoiceMessageInput: () => (
    <button type="button" data-testid="hww-mock-mic">
      Mic
    </button>
  ),
}));

vi.mock("../WorkspaceChatComposerActionsMenu", () => ({
  WorkspaceChatComposerActionsMenu: () => (
    <button type="button" data-testid="hww-mock-attach">
      Add
    </button>
  ),
}));

import { WorkspaceChatComposer } from "../WorkspaceChatComposer";

const baseProps = {
  value: "",
  onChange: vi.fn(),
  onSubmit: vi.fn(),
  disabled: false,
  sending: false,
  voiceTranscribing: false,
  onVoiceBlob: vi.fn(),
  attachments: [],
  onAddAttachments: vi.fn(),
  onRemoveAttachment: vi.fn(),
  catalog: null,
  modelId: null,
  onModelIdChange: vi.fn(),
  exportPdf: { onExport: vi.fn(), busy: false, blockedReason: "none" },
  generateImage: {
    onGenerate: vi.fn(),
    busy: false,
    disabled: true,
    subtitle: "",
  },
  generateVideo: {
    onGenerate: vi.fn(),
    busy: false,
    disabled: true,
    subtitle: "",
  },
};

function renderComposer(overrides: Partial<React.ComponentProps<typeof WorkspaceChatComposer>> = {}) {
  return render(
    <MemoryRouter>
      <div style={{ width: 480 }}>
        <WorkspaceChatComposer {...baseProps} {...overrides} />
      </div>
    </MemoryRouter>,
  );
}

describe("WorkspaceChatComposer plan toggle", () => {
  beforeEach(() => {
    globalThis.ResizeObserver = class {
      constructor(private readonly cb: ResizeObserverCallback) {}
      observe(target: Element): void {
        this.cb([{ target } as ResizeObserverEntry], this);
      }
      unobserve(): void {}
      disconnect(): void {}
    } as unknown as typeof ResizeObserver;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows exactly one Plan toggle default OFF", () => {
    const { container } = renderComposer();
    const toggles = container.querySelectorAll("[data-hww-plan-toggle]");
    expect(toggles.length).toBe(1);
    expect(toggles[0]).toHaveAttribute("aria-pressed", "false");
  });

  it("reflects ON state when planMode is true", () => {
    renderComposer({ planMode: true });
    expect(screen.getByLabelText("Plan mode on")).toHaveAttribute("aria-pressed", "true");
  });

  it("calls onPlanModeChange when clicked", () => {
    const onPlanModeChange = vi.fn();
    const { container } = renderComposer({ planMode: false, onPlanModeChange });
    const toggle = container.querySelector("[data-hww-plan-toggle]") as HTMLButtonElement;
    fireEvent.click(toggle);
    expect(onPlanModeChange).toHaveBeenCalledWith(true);
  });
});
