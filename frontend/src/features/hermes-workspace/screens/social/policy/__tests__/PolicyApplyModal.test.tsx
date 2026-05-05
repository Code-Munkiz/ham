import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { PolicyApplyModal } from "../PolicyApplyModal";
import type {
  SocialPolicyApplyResponse,
  SocialPolicyPreviewResponse,
  SocialPolicyServerError,
} from "../lib/policyTypes";

function previewFixture(overrides: Partial<SocialPolicyPreviewResponse> = {}): SocialPolicyPreviewResponse {
  return {
    effective_before: {} as never,
    effective_after: {} as never,
    diff: [{ path: "providers.x.posting_mode", before: "off", after: "preview" }],
    warnings: [],
    write_target: ".ham/social_policy.json",
    proposal_digest: "abc",
    base_revision: "rev-aaaaaaaaaaaaaaaa",
    live_autonomy_change: false,
    ...overrides,
  };
}

describe("PolicyApplyModal", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <PolicyApplyModal
        open={false}
        preview={previewFixture()}
        writesEnabled
        state={{ kind: "idle" }}
        onApply={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("apply button is disabled until phrase + token are valid", () => {
    const onApply = vi.fn();
    render(
      <PolicyApplyModal
        open
        preview={previewFixture()}
        writesEnabled
        state={{ kind: "idle" }}
        onApply={onApply}
        onClose={vi.fn()}
      />,
    );
    const button = screen.getByRole("button", { name: /save policy/i });
    expect(button).toBeDisabled();

    const phrase = screen.getByLabelText(/Type the confirmation phrase/);
    fireEvent.change(phrase, { target: { value: "SAVE SOCIAL POLICY" } });
    expect(button).toBeDisabled();

    const token = screen.getByLabelText(/Operator write token/);
    fireEvent.change(token, { target: { value: "tok-abc" } });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    expect(onApply).toHaveBeenCalledWith({
      confirmationPhrase: "SAVE SOCIAL POLICY",
      writeToken: "tok-abc",
    });
  });

  it("apply stays disabled when writesEnabled=false", () => {
    render(
      <PolicyApplyModal
        open
        preview={previewFixture()}
        writesEnabled={false}
        state={{ kind: "idle" }}
        onApply={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    const phrase = screen.getByLabelText(/Type the confirmation phrase/);
    fireEvent.change(phrase, { target: { value: "SAVE SOCIAL POLICY" } });
    const token = screen.getByLabelText(/Operator write token/);
    fireEvent.change(token, { target: { value: "tok" } });
    const button = screen.getByRole("button", { name: /save policy/i });
    expect(button).toBeDisabled();
  });

  it("apply stays disabled when live_autonomy_change=true", () => {
    render(
      <PolicyApplyModal
        open
        preview={previewFixture({ live_autonomy_change: true })}
        writesEnabled
        state={{ kind: "idle" }}
        onApply={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    const phrase = screen.getByLabelText(/Type the confirmation phrase/);
    fireEvent.change(phrase, { target: { value: "SAVE SOCIAL POLICY" } });
    const token = screen.getByLabelText(/Operator write token/);
    fireEvent.change(token, { target: { value: "tok" } });
    const button = screen.getByRole("button", { name: /save policy/i });
    expect(button).toBeDisabled();
  });

  it("revision_conflict state shows reload-and-keep-edits CTA", () => {
    const conflictErr: SocialPolicyServerError = {
      status: 409,
      code: "SOCIAL_POLICY_REVISION_CONFLICT",
      message: "drift",
    };
    const onReload = vi.fn();
    render(
      <PolicyApplyModal
        open
        preview={previewFixture()}
        writesEnabled
        state={{ kind: "revision_conflict", error: conflictErr }}
        onApply={vi.fn()}
        onClose={vi.fn()}
        onReloadAndKeepEdits={onReload}
      />,
    );
    const reload = screen.getByRole("button", { name: /reload and keep my edits/i });
    expect(reload).toBeEnabled();
    fireEvent.click(reload);
    expect(onReload).toHaveBeenCalled();
  });

  it("success state shows new revision id", () => {
    const result: SocialPolicyApplyResponse = {
      backup_id: "b-1",
      audit_id: "a-1",
      effective_after: {} as never,
      diff_applied: [],
      new_revision: "rev-bbbbbbbbbbbbbbbb",
      live_autonomy_change: false,
    };
    render(
      <PolicyApplyModal
        open
        preview={previewFixture()}
        writesEnabled
        state={{ kind: "success", result }}
        onApply={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText(/policy saved successfully/i)).toBeInTheDocument();
    expect(screen.getByText(/rev-bbbb/i)).toBeInTheDocument();
  });
});
