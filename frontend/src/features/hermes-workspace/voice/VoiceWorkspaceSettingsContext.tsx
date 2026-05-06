import * as React from "react";
import { fetchVoiceSettings, patchVoiceSettings } from "@/lib/ham/api";
import type { HamVoiceSettingsPayload, HamVoiceSettingsPatch } from "@/lib/ham/types";

type VoiceWorkspaceCtx = {
  payload: HamVoiceSettingsPayload | null;
  loading: boolean;
  error: string | null;
  saving: boolean;
  saveError: string | null;
  refresh: () => Promise<void>;
  updateVoiceSettings: (patch: HamVoiceSettingsPatch) => Promise<void>;
};

const VoiceWorkspaceSettingsContext = React.createContext<VoiceWorkspaceCtx | null>(null);

export function VoiceWorkspaceSettingsProvider(props: { children: React.ReactNode }) {
  const [payload, setPayload] = React.useState<HamVoiceSettingsPayload | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [saveError, setSaveError] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const p = await fetchVoiceSettings();
      setPayload(p);
    } catch (e) {
      setPayload(null);
      setError(e instanceof Error ? e.message : "Failed to load voice settings");
    } finally {
      setLoading(false);
    }
  }, []);

  const updateVoiceSettings = React.useCallback(async (patch: HamVoiceSettingsPatch) => {
    setSaving(true);
    setSaveError(null);
    try {
      const p = await patchVoiceSettings(patch);
      setPayload(p);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Save failed");
      throw e;
    } finally {
      setSaving(false);
    }
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = React.useMemo<VoiceWorkspaceCtx>(
    () => ({ payload, loading, error, saving, saveError, refresh, updateVoiceSettings }),
    [payload, loading, error, saving, saveError, refresh, updateVoiceSettings],
  );

  return (
    <VoiceWorkspaceSettingsContext.Provider value={value}>
      {props.children}
    </VoiceWorkspaceSettingsContext.Provider>
  );
}

export function useVoiceWorkspaceSettings(): VoiceWorkspaceCtx {
  const v = React.useContext(VoiceWorkspaceSettingsContext);
  if (!v) {
    throw new Error("useVoiceWorkspaceSettings must be used within VoiceWorkspaceSettingsProvider");
  }
  return v;
}

/** Safe variant when provider might be absent (should not happen in workspace routes). */
export function useVoiceWorkspaceSettingsOptional(): VoiceWorkspaceCtx | null {
  return React.useContext(VoiceWorkspaceSettingsContext);
}
