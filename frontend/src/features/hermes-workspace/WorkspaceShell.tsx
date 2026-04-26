import * as React from "react";
import { Link, NavLink } from "react-router-dom";
import { Layout, MessageSquare, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { publicAssetUrl } from "@/lib/ham/publicAssets";

type WorkspaceShellProps = {
  children: React.ReactNode;
};

const nav = [
  { to: "/workspace", label: "Home", end: true, icon: Layout },
  { to: "/workspace/chat", label: "Chat", end: false, icon: MessageSquare },
] as const;

export function WorkspaceShell({ children }: WorkspaceShellProps) {
  const logoSrc = publicAssetUrl("ham-logo.png");

  return (
    <div className="hww-root flex h-full min-h-0 w-full min-w-0 flex-col md:flex-row">
      <aside className="hww-sidebar px-3 py-4">
        <div className="mb-6 flex items-center gap-2 px-1">
          <img
            src={logoSrc}
            alt=""
            className="h-7 w-7 object-contain brightness-0 invert opacity-90"
          />
          <div className="min-w-0">
            <p className="truncate text-[10px] font-semibold uppercase tracking-[0.12em] text-white/80">
              Hermes workspace
            </p>
            <p className="hww-pill mt-0.5 w-fit">Lift preview</p>
          </div>
        </div>
        <nav className="flex min-h-0 flex-1 flex-col gap-1">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-lg px-2.5 py-2 text-[13px] font-medium transition-colors",
                  isActive
                    ? "bg-white/[0.1] text-[#e8eef8]"
                    : "text-white/45 hover:bg-white/[0.05] hover:text-white/88",
                )
              }
            >
              <item.icon className="h-4 w-4 shrink-0 opacity-90" strokeWidth={1.5} />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto space-y-2 border-t border-white/[0.08] pt-3">
          <p className="px-1 text-[10px] leading-relaxed text-white/38">
            Production chat stays on <span className="font-mono text-white/50">/chat</span> until
            this lift is promoted.
          </p>
          <Link
            to="/chat"
            className="flex items-center gap-2 rounded-lg border border-white/10 bg-black/20 px-2.5 py-2 text-[11px] text-[#ffb27a]/90 transition-colors hover:border-white/15 hover:bg-white/[0.04]"
          >
            <Sparkles className="h-3.5 w-3.5" strokeWidth={1.5} />
            Open /chat
          </Link>
        </div>
      </aside>
      <div className="hww-main border-white/[0.04] bg-[#030a10]/35 md:border-l">
        {children}
      </div>
    </div>
  );
}
