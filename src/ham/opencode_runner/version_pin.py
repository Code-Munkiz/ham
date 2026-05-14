"""Pinned OpenCode runtime version for the ham-api image.

This constant is the single source of truth for the version HAM expects
the ham-api Cloud Run image to install. It is validated against the
Dockerfile by ``tests/test_opencode_version_pin.py`` so any drift between
the Python pin and the image build fails CI fast.

Bumping process:
1. Update OPENCODE_PINNED_VERSION + OPENCODE_PINNED_LINUX_X64_SHA256 here.
2. Update the matching ARG defaults in the Dockerfile.
3. tests/test_opencode_version_pin.py validates they match.
4. The Dockerfile's build-time ``opencode --version`` gate validates the
   installed binary matches at image-build time.
"""

from __future__ import annotations

OPENCODE_PINNED_VERSION = "1.14.49"
OPENCODE_PINNED_LINUX_X64_SHA256 = (
    "0b373d64650073df36616af189c18cecaa3d5cd19ae2121300cafed1efa54b11"
)

TINI_INSTALL_PATH = "/usr/bin/tini"
