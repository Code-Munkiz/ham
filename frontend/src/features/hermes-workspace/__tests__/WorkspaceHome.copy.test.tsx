import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { WorkspaceHome } from "../WorkspaceHome";

function renderHome() {
  return render(
    <MemoryRouter>
      <WorkspaceHome />
    </MemoryRouter>,
  );
}

describe("WorkspaceHome copy", () => {
  it("renders present-tense product copy in the lead paragraph", () => {
    renderHome();
    expect(screen.getByText(/Mission control for HAM\./i, { selector: "p" })).toBeInTheDocument();
  });

  it("renders present-tense Sessions, Chat, Social, and Surface map tile copy", () => {
    renderHome();
    expect(screen.getByText(/Every conversation, one click away/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Streamed answers, persistent sessions, full repo context/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Plan, draft, and approve posts with policy guardrails/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Every workspace surface, one rail\./i)).toBeInTheDocument();
  });

  it("does not regress to stale future-tense or placeholder phrasing", () => {
    renderHome();
    const banned = [
      /staging placeholders/i,
      /will bind to/i,
      /read-only provider status/i,
      /stream wiring next/i,
      /UI placeholders/i,
    ];
    for (const re of banned) {
      expect(screen.queryByText(re)).not.toBeInTheDocument();
    }
  });

  it("links Chat and Social tiles plus the bottom CTA to /workspace/chat or /workspace/social", () => {
    renderHome();
    const links = screen.getAllByRole("link");
    const hrefs = links.map((a) => a.getAttribute("href"));
    expect(hrefs).toEqual(expect.arrayContaining(["/workspace/chat", "/workspace/social"]));
  });
});
