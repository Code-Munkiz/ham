import type { OperatorMessage } from "./types";

type OperatorMessageListProps = {
  messages: OperatorMessage[];
};

function messageShell(role: OperatorMessage["role"]): string {
  if (role === "user") {
    return "ml-auto border-[#ff6b00]/35 bg-[#ff6b00]/12 text-white";
  }
  if (role === "system") {
    return "mx-auto border-white/20 bg-white/8 text-white";
  }
  return "mr-auto border-white/15 bg-[#0e1822]/75 text-white";
}

export function OperatorMessageList({ messages }: OperatorMessageListProps) {
  return (
    <div className="ow-message-scroll flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
      {messages.map((message) => (
        <article
          key={message.id}
          className={`max-w-[min(94%,52rem)] rounded-2xl border px-3 py-2.5 shadow-[0_8px_24px_rgba(0,0,0,0.18)] ${messageShell(
            message.role,
          )}`}
        >
          <div className="mb-1 flex items-center justify-between gap-3">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-white/55">
              {message.role}
            </span>
            <span className="text-[10px] text-white/45">
              {message.timestamp}
            </span>
          </div>
          <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-5 text-white/95">
            {message.content}
          </pre>
        </article>
      ))}
    </div>
  );
}

