/**
 * Loads `GET /api/chat/attachments/{id}` with Clerk auth and displays as an <img> (blob URL),
 * or renders a caller-supplied blob URL after send (same-tab thumbnails without redundant GET spam).
 */
import * as React from "react";
import { hamApiFetch } from "@/lib/ham/api";

export function WorkspaceChatAuthImage({
  attachmentId,
  alt,
  localPreviewUrl,
}: {
  attachmentId: string;
  alt: string;
  /** Stable blob/object URL keyed by opaque server id — avoids flaky GET across replicas/temp disks. */
  localPreviewUrl?: string | null;
}) {
  const [url, setUrl] = React.useState<string | null>(localPreviewUrl?.trim() || null);
  const [failed, setFailed] = React.useState(false);
  const revokedFetchUrl = React.useRef<string | null>(null);

  React.useEffect(() => {
    const local = (localPreviewUrl || "").trim();
    if (local) {
      setFailed(false);
      setUrl(local);
      return undefined;
    }

    let cancelled = false;

    async function fetchRemote() {
      try {
        const res = await hamApiFetch(`/api/chat/attachments/${encodeURIComponent(attachmentId)}`);
        if (!res.ok) {
          if (!cancelled) setFailed(true);
          return;
        }
        const blob = await res.blob();
        if (cancelled) return;
        const u = URL.createObjectURL(blob);
        revokedFetchUrl.current = u;
        setUrl(u);
      } catch {
        if (!cancelled) setFailed(true);
      }
    }
    void fetchRemote();

    return () => {
      cancelled = true;
      const u = revokedFetchUrl.current;
      revokedFetchUrl.current = null;
      if (u) {
        try {
          URL.revokeObjectURL(u);
        } catch {
          /* ignore */
        }
      }
    };
  }, [attachmentId, localPreviewUrl]);

  if (failed) {
    return (
      <div className="flex h-20 w-28 items-center justify-center rounded-md border border-white/15 bg-black/40 px-1 text-center text-[9px] text-white/45">
        Image unavailable
      </div>
    );
  }
  if (!url) {
    return <div className="h-20 w-28 animate-pulse rounded-md border border-white/10 bg-white/5" />;
  }
  return <img src={url} alt={alt} className="h-full w-full object-cover" />;
}
