/**
 * Loads `GET /api/chat/attachments/{id}` with Clerk auth and displays as an <img> (blob URL).
 */
import * as React from "react";
import { hamApiFetch } from "@/lib/ham/api";

export function WorkspaceChatAuthImage({ attachmentId, alt }: { attachmentId: string; alt: string }) {
  const [url, setUrl] = React.useState<string | null>(null);
  const [failed, setFailed] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await hamApiFetch(`/api/chat/attachments/${encodeURIComponent(attachmentId)}`);
        if (!res.ok) {
          if (!cancelled) setFailed(true);
          return;
        }
        const blob = await res.blob();
        if (cancelled) return;
        setUrl(URL.createObjectURL(blob));
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
      setUrl((current) => {
        if (current) URL.revokeObjectURL(current);
        return null;
      });
    };
  }, [attachmentId]);

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
