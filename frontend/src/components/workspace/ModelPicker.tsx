import * as React from "react";
import { ChevronDown, Check, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ModelOption {
  id: string;
  name: string;
  provider: string;
}

export const MODELS: ModelOption[] = [
  { id: "claude-3-5-sonnet", name: "Claude 3.5 Sonnet", provider: "Anthropic" },
  { id: "claude-3-opus", name: "Claude 3 Opus", provider: "Anthropic" },
  { id: "gpt-4o", name: "GPT-4o", provider: "OpenAI" },
  { id: "gpt-4-turbo", name: "GPT-4 Turbo", provider: "OpenAI" },
  { id: "perplexity-pro", name: "Perplexity Pro", provider: "Perplexity" },
  { id: "llama-3-70b", name: "Llama 3 (70B)", provider: "Meta" },
];

interface ModelPickerProps {
  currentModel: string;
  onSelect: (model: ModelOption) => void;
}

export function ModelPicker({ currentModel, onSelect }: ModelPickerProps) {
  const [isOpen, setIsOpen] = React.useState(false);
  const containerRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="relative w-48" ref={containerRef}>
      <button
        onClick={(e) => {
          e.stopPropagation();
          setIsOpen(!isOpen);
        }}
        className={cn(
          "flex items-center justify-between w-full p-2 pl-3 bg-white/[0.02] border rounded text-[10px] font-bold text-white/60 transition-all uppercase tracking-widest",
          isOpen ? "border-[#FF6B00] bg-white/[0.04]" : "border-white/5 hover:border-white/20",
        )}
      >
        <span className="truncate">{currentModel}</span>
        <ChevronDown
          className={cn("h-3.5 w-3.5 text-white/20 transition-transform", isOpen && "rotate-180")}
        />
      </button>

      {isOpen && (
        <div className="absolute top-full left-0 w-full mt-2 bg-[#0d0d0d] border border-white/10 rounded-lg shadow-2xl z-50 py-2 animate-in fade-in slide-in-from-top-1 duration-200">
          <div className="px-3 py-1 mb-1">
            <span className="text-[8px] font-black text-white/20 uppercase tracking-[0.4em]">
              Select Model
            </span>
          </div>
          <div className="max-h-48 overflow-y-auto scrollbar-hide">
            {MODELS.map((model) => (
              <button
                key={model.id}
                onClick={(e) => {
                  e.stopPropagation();
                  onSelect(model);
                  setIsOpen(false);
                }}
                className={cn(
                  "flex items-center justify-between w-full px-4 py-2 text-[9px] font-bold uppercase tracking-widest transition-colors",
                  currentModel === model.name
                    ? "text-[#FF6B00] bg-[#FF6B00]/5"
                    : "text-white/40 hover:text-white hover:bg-white/5",
                )}
              >
                <span>{model.name}</span>
                {currentModel === model.name && <Check className="h-3 w-3" />}
              </button>
            ))}
          </div>
          <div className="mt-2 pt-2 border-t border-white/5 px-4 flex items-center gap-2">
            <Sparkles className="h-3 w-3 text-[#FF6B00]/40" />
            <span className="text-[8px] font-bold text-white/10 uppercase tracking-widest italic">
              Optimization ready
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
