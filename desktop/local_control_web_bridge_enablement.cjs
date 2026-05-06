"use strict";

function parseEnvFlag(rawValue) {
  const raw = String(rawValue || "")
    .trim()
    .toLowerCase();
  if (!raw) return null;
  if (raw === "1" || raw === "true" || raw === "yes" || raw === "on") return true;
  if (raw === "0" || raw === "false" || raw === "no" || raw === "off") return false;
  return null;
}

/**
 * Bridge defaults:
 * - Packaged desktop: enabled unless explicitly disabled by env flag.
 * - Dev/runtime shell: disabled unless explicitly enabled by env flag.
 */
function localWebBridgeEnabled({ envValue, isPackaged } = {}) {
  const parsed = parseEnvFlag(envValue);
  if (parsed === true) return true;
  if (parsed === false) return false;
  return Boolean(isPackaged);
}

function localWebBridgeDisabledReason({ envValue, isPackaged } = {}) {
  const parsed = parseEnvFlag(envValue);
  if (parsed === false) return "explicit_disabled";
  if (parsed === true) return null;
  return isPackaged ? null : "disabled_by_default_dev";
}

module.exports = {
  parseEnvFlag,
  localWebBridgeEnabled,
  localWebBridgeDisabledReason,
};
