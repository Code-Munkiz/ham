import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ChatContextMetersPayload, ModelCatalogPayload } from "@/lib/ham/types";

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

const catalog: ModelCatalogPayload = {
  items: [
    {
      id: "m1",
      label: "Test chat model",
      tag: null,
      tier: null,
      provider: "test",
      description: "",
      supports_chat: true,
      composer_model_band: "recommended",
    },
  ],
  source: "test",
  gateway_mode: "openrouter",
  openrouter_chat_ready: true,
  dashboard_chat_ready: true,
};

const contextMetersPayload: ChatContextMetersPayload = {
  enabled: true,
  this_turn: {
    fill_ratio: 0.2,
    color: "green",
    unit: "estimate_tokens",
    used: 100,
    limit: 1000,
    model_id: "m1",
  },
  workspace: {
    fill_ratio: 0.3,
    color: "amber",
    bottleneck_role: null,
    source: "local",
    used: 100,
    limit: 1000,
    unit: "chars",
  },
  thread: {
    fill_ratio: 0.1,
    color: "green",
    approx_transcript_chars: 50,
    thread_budget_chars: 5000,
    unit: "chars_estimate",
  },
};

function renderAtWidth(px: number) {
  return render(
    <MemoryRouter>
      <div style={{ width: px }}>
        <WorkspaceChatComposer
          value=""
          onChange={() => {}}
          onSubmit={() => {}}
          disabled={false}
          sending={false}
          voiceTranscribing={false}
          onVoiceBlob={() => {}}
          attachments={[]}
          onAddAttachments={() => {}}
          onRemoveAttachment={() => {}}
          catalog={catalog}
          modelId="m1"
          onModelIdChange={() => {}}
          exportPdf={{ onExport: () => {}, busy: false, blockedReason: "none" }}
          generateImage={{
            onGenerate: () => {},
            busy: false,
            disabled: true,
            subtitle: "",
          }}
          generateVideo={{
            onGenerate: () => {},
            busy: false,
            disabled: true,
            subtitle: "",
          }}
          contextMetersEnabled
          contextMetersPayload={contextMetersPayload}
        />
      </div>
    </MemoryRouter>,
  );
}

describe("WorkspaceChatComposer narrow layout", () => {
  const gbcrOrig = HTMLElement.prototype.getBoundingClientRect;

  beforeEach(() => {
    globalThis.ResizeObserver = class {
      constructor(private readonly cb: ResizeObserverCallback) {}
      observe(target: Element): void {
        this.cb([{ target } as ResizeObserverEntry], this);
      }
      unobserve(): void {}
      disconnect(): void {}
    } as unknown as typeof ResizeObserver;
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (
      this: HTMLElement,
    ) {
      if (this.classList.contains("hww-chat-composer-outer")) {
        const raw = (this.parentElement as HTMLElement | null)?.style?.width ?? "";
        const n = Number.parseFloat(String(raw));
        const width = Number.isFinite(n) && n > 0 ? n : 480;
        return {
          width,
          height: 100,
          top: 0,
          left: 0,
          right: width,
          bottom: 100,
          x: 0,
          y: 0,
          toJSON: () => ({}),
        } as DOMRect;
      }
      return gbcrOrig.call(this);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("exposes compact density when outer width is below 500px", async () => {
    renderAtWidth(420);
    const outer = document.querySelector(".hww-chat-composer-outer");
    expect(outer).toBeTruthy();
    await waitFor(() => {
      expect(outer?.getAttribute("data-hww-composer-density")).toBe("compact");
    });
    expect(screen.getByRole("button", { name: "Model" })).toBeInTheDocument();
    expect(screen.getByTestId("hww-mock-mic")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument();
    await waitFor(() => {
      expect(document.querySelector('[data-hww-system-pulse="true"]')).toBeTruthy();
    });
  });

  it("uses separate rings when width is comfortable", async () => {
    renderAtWidth(520);
    const outer = document.querySelector(".hww-chat-composer-outer");
    await waitFor(() => {
      expect(outer?.getAttribute("data-hww-composer-density")).toBe("comfortable");
    });
    await waitFor(() => {
      expect(document.querySelector('[data-hww-meter-cluster="rings"]')).toBeTruthy();
    });
    const deck = document.querySelector(".hww-command-deck");
    expect(deck?.getAttribute("data-hww-command-deck-layout")).toBe("triple");
    expect(deck?.className).toMatch(/items-end/);
    expect(deck?.className).toMatch(/minmax\(0,1fr\)/);
    expect(document.querySelector("[data-hww-command-input-slot]")).toBeTruthy();
    expect(document.querySelector("[data-hww-command-deck-actions]")).toBeTruthy();
  });

  it("aligns command deck controls to center row when density is compact (pulse)", async () => {
    renderAtWidth(420);
    const outer = document.querySelector(".hww-chat-composer-outer");
    await waitFor(() => {
      expect(outer?.getAttribute("data-hww-composer-density")).toBe("compact");
    });
    const deck = document.querySelector(".hww-command-deck");
    expect(deck?.getAttribute("data-hww-command-deck-layout")).toBe("triple");
    expect(deck?.className).toMatch(/items-center/);
  });

  it("exposes tight density when outer width is below 400px", async () => {
    renderAtWidth(360);
    const outer = document.querySelector(".hww-chat-composer-outer");
    expect(outer).toBeTruthy();
    await waitFor(() => {
      expect(outer?.getAttribute("data-hww-composer-density")).toBe("tight");
    });
    expect(screen.getByRole("button", { name: /Model:/i })).toBeInTheDocument();
  });
});
