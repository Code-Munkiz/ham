import * as React from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";

const BG = "#0d0d0d";
const CURSOR = "#ea580c";
const FORE = "#e6e6e6";

export type XtermControl = {
  write: (s: string) => void;
  fit: () => void;
  focus: () => void;
  getDimensions: () => { cols: number; rows: number };
};

type Props = {
  tabId: string;
  isActive: boolean;
  isMobile: boolean;
  onReady: (tabId: string, ctrl: XtermControl | null) => void;
  onPtyData: (tabId: string, data: string) => void;
};

/**
 * One xterm instance per tab; buffer preserved when the tab is hidden (stacked absolute panes).
 */
export function WorkspaceXtermHost({ tabId, isActive, isMobile, onReady, onPtyData }: Props) {
  const elRef = React.useRef<HTMLDivElement | null>(null);
  const termRef = React.useRef<Terminal | null>(null);
  const fitRef = React.useRef<FitAddon | null>(null);
  const onPtyDataRef = React.useRef(onPtyData);
  onPtyDataRef.current = onPtyData;

  const layout = React.useCallback(() => {
    const t = termRef.current;
    const f = fitRef.current;
    if (!t || !f) return;
    try {
      f.fit();
    } catch {
      /* ignore */
    }
  }, []);

  const isMobileRef = React.useRef(isMobile);
  isMobileRef.current = isMobile;
  const onReadyRef = React.useRef(onReady);
  onReadyRef.current = onReady;

  React.useLayoutEffect(() => {
    const el = elRef.current;
    if (!el) return;

    const term = new Terminal({
      allowProposedApi: true,
      cursorBlink: true,
      fontSize: 13,
      lineHeight: 1.2,
      fontFamily: "ui-monospace, Consolas, 'Cascadia Mono', 'Segoe UI Mono', monospace",
      theme: {
        background: BG,
        foreground: FORE,
        cursor: CURSOR,
        selectionBackground: "rgba(234, 88, 12, 0.35)",
      },
      disableStdin: isMobileRef.current,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(el);
    fit.fit();

    const ctrl: XtermControl = {
      write: (s) => {
        try {
          term.write(s);
        } catch {
          /* ignore */
        }
      },
      fit: () => {
        try {
          fit.fit();
        } catch {
          /* ignore */
        }
      },
      focus: () => {
        try {
          term.focus();
        } catch {
          /* ignore */
        }
      },
      getDimensions: () => ({ cols: term.cols, rows: term.rows }),
    };

    const dataDisp = term.onData((d) => {
      if (isMobileRef.current) return;
      onPtyDataRef.current(tabId, d);
    });

    termRef.current = term;
    fitRef.current = fit;
    onReadyRef.current(tabId, ctrl);

    return () => {
      dataDisp.dispose();
      onReadyRef.current(tabId, null);
      try {
        term.dispose();
      } catch {
        /* ignore */
      }
      termRef.current = null;
      fitRef.current = null;
    };
  }, [tabId]);

  React.useLayoutEffect(() => {
    if (termRef.current) {
      try {
        termRef.current.options.disableStdin = isMobile;
      } catch {
        /* ignore */
      }
    }
  }, [isMobile]);

  React.useLayoutEffect(() => {
    if (!isActive) return;
    const t = requestAnimationFrame(() => {
      layout();
    });
    return () => cancelAnimationFrame(t);
  }, [isActive, layout]);

  return (
    <div
      ref={elRef}
      className="hww-scroll h-full min-h-0 w-full min-w-0 p-0"
      data-ham-xterm
      onMouseDownCapture={() => {
        if (isActive && !isMobile) termRef.current?.focus();
      }}
    />
  );
}
