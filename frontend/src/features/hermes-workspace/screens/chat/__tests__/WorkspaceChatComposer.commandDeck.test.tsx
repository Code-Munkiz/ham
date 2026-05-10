import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { WorkspaceChatComposer } from "../WorkspaceChatComposer";
import type { ModelCatalogPayload } from "@/lib/ham/types";

vi.mock("../WorkspaceVoiceMessageInput", () => ({
  WorkspaceVoiceMessageInput: () => <div data-hww-voice-mock />,
}));

vi.mock("../WorkspaceChatComposerActionsMenu", () => ({
  WorkspaceChatComposerActionsMenu: () => (
    <button type="button" data-hww-actions-mock>
      Add
    </button>
  ),
}));

const baseItem = {
  tag: null,
  tier: null,
  provider: "openrouter",
  description: "",
};

const mockCatalog: ModelCatalogPayload = {
  items: [
    {
      ...baseItem,
      id: "openrouter/ham-test-model",
      label: "HAM test model",
      supports_chat: true,
      composer_model_band: "recommended",
    },
  ],
  source: "test",
  gateway_mode: "mock",
  openrouter_chat_ready: true,
  dashboard_chat_ready: true,
};

const noopPdf = { onExport: () => {}, busy: false, blockedReason: "none" as const };
const noopGen = { onGenerate: () => {}, busy: false, disabled: true, subtitle: "n/a" };

describe("WorkspaceChatComposer command deck", () => {
  it("exposes command deck data attributes and compact send control", () => {
    render(
      <MemoryRouter>
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
          catalog={mockCatalog}
          modelId="openrouter/ham-test-model"
          onModelIdChange={() => {}}
          exportPdf={noopPdf}
          generateImage={noopGen}
          generateVideo={noopGen}
          contextMetersEnabled={false}
        />
      </MemoryRouter>,
    );
    expect(document.querySelector("[data-hww-command-deck]")).toBeTruthy();
    expect(document.querySelector('[data-hww-composer-density]')).toBeTruthy();
    const send = document.querySelector('[data-hww-composer-send]');
    expect(send).toBeTruthy();
    expect(send?.classList.contains("h-9")).toBe(true);
    expect(send?.classList.contains("w-9")).toBe(true);
    expect(send?.querySelector('svg')).toBeTruthy();
  });

  it("shows model picker trigger and add actions when gateway exposes models", () => {
    render(
      <MemoryRouter>
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
          catalog={mockCatalog}
          modelId="openrouter/ham-test-model"
          onModelIdChange={() => {}}
          exportPdf={noopPdf}
          generateImage={noopGen}
          generateVideo={noopGen}
          contextMetersEnabled={false}
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole("button", { name: "Model" })).toBeTruthy();
    expect(document.querySelector("[data-hww-voice-mock]")).toBeTruthy();
  });
});
