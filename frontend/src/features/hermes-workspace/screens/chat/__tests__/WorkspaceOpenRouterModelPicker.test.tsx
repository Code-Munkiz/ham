import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { WorkspaceOpenRouterModelPicker } from "../WorkspaceOpenRouterModelPicker";
import type { ModelCatalogPayload } from "@/lib/ham/types";

function baseCatalog(gatewayMode: "http" | "openrouter"): ModelCatalogPayload {
  return {
    source: "cursor_api",
    gateway_mode: gatewayMode,
    openrouter_chat_ready: gatewayMode === "openrouter",
    http_chat_ready: gatewayMode === "http",
    dashboard_chat_ready: true,
    items: [],
    openrouter_catalog: null,
  };
}

const candidates = [
  {
    id: "tier:auto",
    label: "Auto",
    tag: "EFFICIENCY",
    tier: "auto",
    provider: "openrouter",
    description: "auto model",
    supports_chat: true,
    disabled_reason: null,
    openrouter_model: "openrouter/openai/gpt-4o-mini",
    composer_model_band: "recommended" as const,
  },
];

describe("WorkspaceOpenRouterModelPicker", () => {
  it("shows Hermes default label when gateway mode is http and no model selected", () => {
    render(
      <MemoryRouter>
        <WorkspaceOpenRouterModelPicker
          catalog={baseCatalog("http")}
          candidates={candidates}
          modelId={null}
          onModelIdChange={() => {}}
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole("button", { name: "Model" })).toHaveTextContent(
      "Hermes Agent / Default",
    );
  });

  it("shows first candidate label when gateway mode is openrouter and no model selected", () => {
    render(
      <MemoryRouter>
        <WorkspaceOpenRouterModelPicker
          catalog={baseCatalog("openrouter")}
          candidates={candidates}
          modelId={null}
          onModelIdChange={() => {}}
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole("button", { name: "Model" })).toHaveTextContent("Auto");
  });
});
