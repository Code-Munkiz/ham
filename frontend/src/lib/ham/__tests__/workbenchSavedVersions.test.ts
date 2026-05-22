import { describe, expect, it } from "vitest";
import type { BuilderSourceSnapshotRecord } from "@/lib/ham/api";
import {
  formatSavedVersionCreatedAt,
  sanitizeSavedVersionsErrorMessage,
  savedVersionFileCount,
  savedVersionFilesChangedCopy,
  savedVersionLabel,
  savedVersionsCopyLooksSafe,
  sortSavedVersionsNewestFirst,
} from "@/lib/ham/workbenchSavedVersions";

function snapshot(partial: Partial<BuilderSourceSnapshotRecord>): BuilderSourceSnapshotRecord {
  return {
    id: "ssnp_hidden",
    project_id: "proj_abc",
    workspace_id: "ws_abc",
    project_source_id: "psrc_1",
    status: "materialized",
    digest_sha256: "abc",
    size_bytes: 100,
    artifact_uri: "builder-artifact://hidden",
    manifest: {},
    created_at: "2026-01-01T00:00:00Z",
    created_by: "user_a",
    metadata: {},
    ...partial,
  };
}

describe("workbenchSavedVersions", () => {
  it("sorts snapshots newest first", () => {
    const rows = sortSavedVersionsNewestFirst([
      snapshot({ id: "a", created_at: "2026-01-01T00:00:00Z" }),
      snapshot({ id: "b", created_at: "2026-01-02T00:00:00Z" }),
    ]);
    expect(rows.map((row) => row.id)).toEqual(["b", "a"]);
  });

  it("reads file counts from manifest metadata", () => {
    expect(savedVersionFileCount(snapshot({ manifest: { file_count: 4 } }))).toBe(4);
    expect(
      savedVersionFileCount(
        snapshot({
          manifest: {
            entries: [{ path: "src/App.tsx" }, { path: "src/main.tsx" }],
          },
        }),
      ),
    ).toBe(2);
    expect(savedVersionFilesChangedCopy(3)).toBe("3 files");
  });

  it("uses normie-friendly labels without exposing snapshot ids", () => {
    expect(savedVersionLabel(snapshot({ id: "ssnp_secret" }), { sequence: 1 })).toBe(
      "Latest saved version",
    );
    expect(
      savedVersionLabel(snapshot({ id: "ssnp_secret" }), { isCurrent: true, sequence: 2 }),
    ).toBe("Current saved version");
    expect(formatSavedVersionCreatedAt("2026-01-01T12:00:00Z")).toMatch(/2026/);
  });

  it("sanitizes load errors and flags internal leakage", () => {
    expect(sanitizeSavedVersionsErrorMessage("ssnp_abc builder-artifact://x")).toMatch(
      /could not load saved versions/i,
    );
    expect(savedVersionsCopyLooksSafe("Saved version · Created Jan 1")).toBe(true);
    expect(savedVersionsCopyLooksSafe("ssnp_abc")).toBe(false);
  });
});
