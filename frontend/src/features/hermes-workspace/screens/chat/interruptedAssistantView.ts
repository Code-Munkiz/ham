export const INTERRUPTED_SUFFIX = "\n\nConnection interrupted. Ask me to continue.";
export const INTERRUPTED_EMPTY =
  "Connection interrupted before any content was saved. Ask me to continue.";

export type InterruptedAssistantView = {
  visibleContent: string;
  interrupted: boolean;
};

export function interruptedAssistantView(content: string): InterruptedAssistantView {
  if (content === INTERRUPTED_EMPTY) {
    return { visibleContent: "", interrupted: true };
  }
  if (content.endsWith(INTERRUPTED_SUFFIX)) {
    return {
      visibleContent: content.slice(0, -INTERRUPTED_SUFFIX.length).trimEnd(),
      interrupted: true,
    };
  }
  return { visibleContent: content, interrupted: false };
}
