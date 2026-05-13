#!/usr/bin/env python3
"""Plan or execute ``gsutil cp`` upload for preview source bundles.

Default **dry-run**: prints the command only (no credentials required).

Use ``--apply`` only after explicit operator authorization.
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload preview bundle to GCS (dry-run by default).")
    parser.add_argument("--bucket-uri", required=True, help="gs://bucket/prefix path (no secrets)")
    parser.add_argument("--zip-path", required=True, help="Local zip path")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Run gsutil (requires authenticated operator shell)",
    )
    args = parser.parse_args()

    bucket = args.bucket_uri.strip()
    if not bucket.startswith("gs://"):
        print("bucket-uri must start with gs://", file=sys.stderr)
        return 2

    cmd = ["gsutil", "cp", args.zip_path, bucket.rstrip("/") + "/preview-source.zip"]
    printable = " ".join(cmd)
    if not args.apply:
        print(f"DRY-RUN (would execute): {printable}")
        return 0

    subprocess.run(cmd, check=True)
    print(f"Uploaded via: {printable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
