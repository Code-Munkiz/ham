import * as React from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

interface CollapsibleSectionProps {
  title: string;
  count?: number;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

export function CollapsibleSection({ title, count, children, defaultOpen = false }: CollapsibleSectionProps) {
  const [isOpen, setIsOpen] = React.useState(defaultOpen);

  return (
    <div className="border-b border-white/5 last:border-0">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-4 hover:bg-white/[0.02] transition-colors group"
      >
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-black text-white/40 uppercase tracking-[0.3em] group-hover:text-white/60 transition-colors">
            {title}
          </span>
          {count !== undefined && (
            <span className="text-[9px] font-mono text-[#FF6B00]/60 bg-[#FF6B00]/5 px-1.5 py-0.5 rounded border border-[#FF6B00]/10">
              {count.toString().padStart(2, '0')}
            </span>
          )}
        </div>
        {isOpen ? (
          <ChevronDown className="h-3 w-3 text-white/20 group-hover:text-white/40" />
        ) : (
          <ChevronRight className="h-3 w-3 text-white/20 group-hover:text-white/40" />
        )}
      </button>
      
      {isOpen && (
        <div className="p-4 pt-0 animate-in fade-in slide-in-from-top-1 duration-200">
          {children}
        </div>
      )}
    </div>
  );
}
