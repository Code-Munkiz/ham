import type { OperatorMessage } from "./types";

type OperatorMessageListProps = {
  messages: OperatorMessage[];
};

function roleLabel(role: OperatorMessage["role"]): string {
  if (role === "user") return "You";
  if (role === "system") return "System";
  return "Assistant";
}

function messageShell(role: OperatorMessage["role"]): string {
  if (role === "user") {
    return "ow-bubble-user ml-auto border-[#c45c12]/50 bg-gradient-to-b from-[#1a120a]/95 to-[#0f0c09]/90 text-white shadow-[0_10px_32px_rgba(0,0,0,0.35)]";
  }
  if (role === "system") {
    return "ow-bubble-system mx-auto border-amber-500/25 bg-amber-500/5 text-amber-50/90";
  }
  return "ow-bubble-assistant mr-auto border-white/[0.1] bg-[#0a1218]/90 text-white shadow-[0_8px_28px_rgba(0,0,0,0.28)]";
}

export function OperatorMessageList({ messages }: OperatorMessageListProps) {
  return (
    <div className="ow-message-scroll flex min-h-0 flex-1 flex-col gap-3.5 overflow-y-auto overflow-x-hidden pr-1">
      {messages.map((message) => (
        <article
          key={message.id}
          className={`max-w-[min(94%,40rem)] rounded-[1.1rem] border px-3.5 py-3 ${messageShell(
            message.role,
          )}`}
        >
          <div className="mb-1.5 flex items-center justify-between gap-3">
            <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-white/50">
              {roleLabel(message.role)}
            </span>
            <span className="text-[10px] tabular-nums text-white/40">
              {message.timestamp}
            </span>
          </div>
          <pre className="whitespace-pre-wrap break-words font-sans text-[0.8125rem] leading-relaxed text-white/92">
            {message.content}
          </pre>
        </article>
      ))}
    </div>
  );
}

