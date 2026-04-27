'use strict';

/**
 * Desktop Local Control Phase 3A — mocked sidecar status only.
 * No child process, no stdio, no network. Constants for doctor/UI/CLI alignment.
 */

const KIND = 'ham_desktop_local_control_sidecar_status';

function buildMockSidecarStatus() {
  return {
    kind: KIND,
    expected: true,
    implemented: false,
    mode: 'mock_status_only',
    transport: 'stdio_json_rpc_planned',
    inbound_network: false,
    running: false,
    droid_access: 'not_enabled',
    capabilities: {
      browser_automation: 'not_implemented',
      filesystem_access: 'not_implemented',
      shell_commands: 'not_implemented',
      app_window_control: 'not_implemented',
      mcp_adapters: 'not_implemented',
    },
  };
}

module.exports = {
  KIND,
  buildMockSidecarStatus,
};
