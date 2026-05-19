import { render } from "@testing-library/react";
import { MemoryRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

function LocationProbe({ onLocation }: { onLocation: (path: string, search: string) => void }) {
  const loc = useLocation();
  onLocation(loc.pathname, loc.search);
  return null;
}

function renderWithRedirects(initialPath: string) {
  let observed: { pathname: string; search: string } = { pathname: "", search: "" };
  const onLocation = (pathname: string, search: string) => {
    observed = { pathname, search };
  };

  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route
          path="/workspace/coding-agents"
          element={<Navigate to="/workspace/builder-studio" replace />}
        />
        <Route
          path="/workspace/builder-studio"
          element={<Navigate to="/workspace/settings?section=builders" replace />}
        />
        <Route
          path="/workspace/builder-studio/:builderId"
          element={<Navigate to="/workspace/settings?section=builders" replace />}
        />
        <Route path="/workspace/settings" element={<LocationProbe onLocation={onLocation} />} />
      </Routes>
    </MemoryRouter>,
  );

  return observed;
}

describe("Builder Studio route redirects", () => {
  it("redirects /workspace/builder-studio to settings builders section", () => {
    const observed = renderWithRedirects("/workspace/builder-studio");
    expect(observed.pathname).toBe("/workspace/settings");
    expect(observed.search).toBe("?section=builders");
  });

  it("redirects /workspace/builder-studio/:builderId to settings builders section", () => {
    const observed = renderWithRedirects("/workspace/builder-studio/some-id");
    expect(observed.pathname).toBe("/workspace/settings");
    expect(observed.search).toBe("?section=builders");
  });

  it("redirects legacy /workspace/coding-agents through builder-studio to builders section", () => {
    const observed = renderWithRedirects("/workspace/coding-agents");
    expect(observed.pathname).toBe("/workspace/settings");
    expect(observed.search).toBe("?section=builders");
  });
});
