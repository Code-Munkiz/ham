import React, { useState, useMemo } from 'react';
import { ScrollText, Search as SearchIcon, ChevronDown, ChevronUp, Terminal as TerminalIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

interface LogEntry {
  id: string;
  timestamp: string;
  level: 'INFO' | 'WARN' | 'ERROR' | 'DEBUG';
  source: 'hermes' | 'bridge' | 'droid' | 'system';
  run_id: string;
  message: string;
  detail?: string;
}

const MOCK_LOGS: LogEntry[] = [
  { id: '1', timestamp: '2026-04-19T14:23:01Z', level: 'INFO', source: 'hermes', run_id: 'run-abc123def456', message: 'Intent profile selected: inspect_repo_v1' },
  { id: '2', timestamp: '2026-04-19T14:23:05Z', level: 'INFO', source: 'bridge', run_id: 'run-abc123def456', message: 'Validation gate passed — 1 command scheduled' },
  { id: '3', timestamp: '2026-04-19T14:23:10Z', level: 'INFO', source: 'droid', run_id: 'run-abc123def456', message: 'Executing: git diff --name-only' },
  { id: '4', timestamp: '2026-04-19T14:23:15Z', level: 'WARN', source: 'bridge', run_id: 'run-abc123def456', message: 'Command timeout approaching (4.1s / 5s limit)', detail: 'Warning: Bridge processing taking longer than nominal thresholds. Possible network jitter or heavy I/O detected on target node.' },
  { id: '5', timestamp: '2026-04-19T14:23:20Z', level: 'ERROR', source: 'droid', run_id: 'run-abc123def456', message: 'Subprocess exited with code 1 — stdout captured', detail: 'error: could not create work tree: No such file or directory\nfatal: failed to copy file to .ham/temp/bridge_sync' },
  { id: '6', timestamp: '2026-04-19T14:24:00Z', level: 'INFO', source: 'hermes', run_id: 'run-uvw789xyz012', message: 'Hermes review complete — ok: true' },
  { id: '7', timestamp: '2026-04-19T14:24:05Z', level: 'DEBUG', source: 'system', run_id: 'run-uvw789xyz012', message: 'Run persisted: .ham/runs/20260419T142301Z-run-abc123.json' },
  { id: '8', timestamp: '2026-04-19T14:25:01Z', level: 'INFO', source: 'hermes', run_id: 'run-ghj456klm789', message: 'Intent profile selected: review_diff_v1' },
  { id: '9', timestamp: '2026-04-19T14:25:10Z', level: 'INFO', source: 'bridge', run_id: 'run-ghj456klm789', message: 'Mapping project profile: Alpha Team' },
  { id: '10', timestamp: '2026-04-19T14:25:15Z', level: 'INFO', source: 'droid', run_id: 'run-ghj456klm789', message: 'Unit 04 active: beginning scan' },
  { id: '11', timestamp: '2026-04-19T14:26:01Z', level: 'DEBUG', source: 'system', run_id: 'run-uvw789xyz012', message: 'Kernel garbage collection initiated' },
  { id: '12', timestamp: '2026-04-19T14:26:10Z', level: 'INFO', source: 'bridge', run_id: 'run-abc123def456', message: 'Resource reclaimed: bridge_session_88' },
  { id: '13', timestamp: '2026-04-19T14:27:01Z', level: 'INFO', source: 'hermes', run_id: 'run-iop987qwe321', message: 'Intent profile selected: audit_security_v2' },
  { id: '14', timestamp: '2026-04-19T14:27:05Z', level: 'WARN', source: 'droid', run_id: 'run-iop987qwe321', message: 'Low memory warning on workspace droid' },
  { id: '15', timestamp: '2026-04-19T14:27:10Z', level: 'INFO', source: 'system', run_id: 'run-iop987qwe321', message: 'Allocating additional workspace buffer' },
  { id: '16', timestamp: '2026-04-19T14:28:01Z', level: 'INFO', source: 'hermes', run_id: 'run-ghj456klm789', message: 'Hermes review complete — ok: true' },
  { id: '17', timestamp: '2026-04-19T14:28:10Z', level: 'DEBUG', source: 'bridge', run_id: 'run-ghj456klm789', message: 'Syncing deltas to remote endpoint' },
  { id: '18', timestamp: '2026-04-19T14:29:01Z', level: 'ERROR', source: 'system', run_id: 'run-non-assigned', message: 'Failed to resolve author identity for orphaned run', detail: 'Identity error: Provider token expired or invalid. Re-auth required for droid escalation.' },
  { id: '19', timestamp: '2026-04-19T14:30:05Z', level: 'INFO', source: 'droid', run_id: 'run-iop987qwe321', message: 'Executing: security-audit --depth full' },
  { id: '20', timestamp: '2026-04-19T14:31:01Z', level: 'INFO', source: 'hermes', run_id: 'run-iop987qwe321', message: 'Hermes review complete — ok: true' },
  { id: '21', timestamp: '2026-04-19T14:32:01Z', level: 'DEBUG', source: 'system', run_id: 'run-iop987qwe321', message: 'Artifacts archived to .ham/archive/run-iop987.zip' },
  { id: '22', timestamp: '2026-04-19T14:33:01Z', level: 'INFO', source: 'hermes', run_id: 'run-rty555vbn444', message: 'Intent profile selected: generate_docs_v1' },
  { id: '23', timestamp: '2026-04-19T14:33:10Z', level: 'INFO', source: 'droid', run_id: 'run-rty555vbn444', message: 'Synthesizing markdown from logic deltas' },
  { id: '24', timestamp: '2026-04-19T14:33:15Z', level: 'WARN', source: 'system', run_id: 'run-rty555vbn444', message: 'High CPU utilization detected during synth' },
  { id: '25', timestamp: '2026-04-19T14:34:01Z', level: 'INFO', source: 'bridge', run_id: 'run-rty555vbn444', message: 'Directives pushed to upstream — 5 files modified' },
];

export default function Logs() {
  const [search, setSearch] = useState('');
  const [level, setLevel] = useState<'ALL' | 'INFO' | 'WARN' | 'ERROR' | 'DEBUG'>('ALL');
  const [source, setSource] = useState<'ALL' | 'HERMES' | 'BRIDGE' | 'DROID' | 'SYSTEM'>('ALL');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const filteredLogs = useMemo(() => {
    return MOCK_LOGS.filter((entry) => {
      const matchesSearch = entry.message.toLowerCase().includes(search.toLowerCase()) || 
                            entry.run_id.toLowerCase().includes(search.toLowerCase());
      const matchesLevel = level === 'ALL' || entry.level === level;
      const matchesSource = source === 'ALL' || entry.source === source.toLowerCase();
      return matchesSearch && matchesLevel && matchesSource;
    }).sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  }, [search, level, source]);

  const clearFilters = () => {
    setSearch('');
    setLevel('ALL');
    setSource('ALL');
  };

  const isFiltered = search !== '' || level !== 'ALL' || source !== 'ALL';

  const getLevelStyles = (lvl: string) => {
    switch (lvl) {
      case 'INFO': return 'bg-blue-500/10 text-blue-400';
      case 'WARN': return 'bg-yellow-500/10 text-yellow-400';
      case 'ERROR': return 'bg-red-500/10 text-red-400';
      case 'DEBUG': return 'bg-white/5 text-white/20';
      default: return 'bg-white/5 text-white/50';
    }
  };

  return (
    <div className="h-full flex flex-col bg-[#050505] font-sans overflow-hidden">
      {/* Grid Pattern */}
      <div 
        className="fixed inset-0 pointer-events-none opacity-[0.02]" 
        style={{ backgroundImage: 'linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)', backgroundSize: '64px 64px' }} 
      />

      <div className="p-8 space-y-8 max-w-full w-full animate-in fade-in duration-700 relative z-10 flex-1 flex flex-col min-h-0">
        {/* Header */}
        <div className="flex items-center justify-between pb-6 border-b border-white/10 shrink-0">
          <div className="flex items-center gap-4">
            <div className="bg-[#FF6B00]/10 border border-[#FF6B00]/20 rounded p-2">
              <ScrollText className="h-6 w-6 text-[#FF6B00]" />
            </div>
            <div>
              <h1 className="text-4xl font-black text-white italic tracking-tighter uppercase leading-none">
                System <span className="text-[#FF6B00] not-italic">Logs</span>
              </h1>
              <div className="mt-2 flex items-center gap-2">
                <span className="text-[10px] font-black uppercase tracking-[0.3em] text-white/60">Real-time Stream</span>
                <span className="bg-green-500/10 text-green-500 px-1.5 py-0.5 rounded text-[8px] font-black uppercase">
                  {MOCK_LOGS.length} Entries
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="space-y-4 shrink-0">
          <div className="flex flex-wrap items-center gap-4">
            <div className="relative flex-1 min-w-[300px]">
              <SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white/20" />
              <input 
                type="text" 
                placeholder="SEARCH MESSAGE OR RUN_ID..." 
                className="w-full bg-black/40 border border-white/5 rounded pl-10 pr-3 py-2 text-[11px] font-bold text-white uppercase tracking-widest focus:outline-none focus:border-[#FF6B00]/40 transition-colors"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>

            <div className="flex items-center gap-2">
              <span className="text-[8px] font-black uppercase tracking-widest text-white/20">Level:</span>
              <div className="flex bg-[#0a0a0a] rounded border border-white/5 p-1 gap-1">
                {(['ALL', 'INFO', 'WARN', 'ERROR', 'DEBUG'] as const).map((lvl) => (
                  <button
                    key={lvl}
                    onClick={() => setLevel(lvl)}
                    className={cn(
                      "px-3 py-1 text-[9px] font-black uppercase tracking-widest rounded transition-all",
                      level === lvl ? "bg-[#FF6B00] text-black" : "text-white/30 hover:text-white"
                    )}
                  >
                    {lvl}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-[8px] font-black uppercase tracking-widest text-white/20">Source:</span>
              <select 
                className="bg-black/40 border border-white/5 rounded px-3 py-2 text-[11px] font-bold text-white uppercase tracking-widest focus:outline-none focus:border-[#FF6B00]/40 appearance-none min-w-[120px]"
                value={source}
                onChange={(e) => setSource(e.target.value as any)}
              >
                {(['ALL', 'HERMES', 'BRIDGE', 'DROID', 'SYSTEM'] as const).map((src) => (
                  <option key={src} value={src}>{src}</option>
                ))}
              </select>
            </div>

            {isFiltered && (
              <button 
                onClick={clearFilters}
                className="text-[10px] font-black uppercase tracking-widest text-white/40 hover:text-white transition-colors"
              >
                Clear Filters
              </button>
            )}
          </div>

          <p className="text-[9px] font-black uppercase tracking-widest text-white/20">
            Showing {filteredLogs.length} of {MOCK_LOGS.length} entries
          </p>
        </div>

        {/* Log Table */}
        <div className="flex-1 bg-[#0a0a0a] border border-white/5 rounded-xl overflow-hidden flex flex-col min-h-0">
          <div className="grid grid-cols-[160px_100px_100px_160px_1fr] p-4 border-b border-white/10 bg-[#0d0d0d] shrink-0">
            <span className="text-[10px] font-black uppercase tracking-widest text-white/40">Timestamp</span>
            <span className="text-[10px] font-black uppercase tracking-widest text-white/40">Level</span>
            <span className="text-[10px] font-black uppercase tracking-widest text-white/40">Source</span>
            <span className="text-[10px] font-black uppercase tracking-widest text-white/40">Run ID</span>
            <span className="text-[10px] font-black uppercase tracking-widest text-white/40">Message</span>
          </div>
          
          <div className="flex-1 overflow-y-auto min-h-0 pb-10">
            {filteredLogs.map((log) => (
              <React.Fragment key={log.id}>
                <div 
                  className={cn(
                    "grid grid-cols-[160px_100px_100px_160px_1fr] p-4 border-b border-white/[0.02] items-center cursor-pointer transition-colors",
                    log.level === 'ERROR' ? "bg-red-500/[0.02] hover:bg-red-500/[0.04]" : 
                    log.level === 'WARN' ? "bg-yellow-500/[0.02] hover:bg-yellow-500/[0.04]" : 
                    "bg-[#080808] hover:bg-white/[0.04]"
                  )}
                  onClick={() => setExpandedId(expandedId === log.id ? null : log.id)}
                >
                  <span className="font-mono text-[10px] text-white/30">{log.timestamp}</span>
                  <div className="px-2">
                    <span className={cn(
                      "px-2 py-0.5 rounded text-[8px] font-black font-mono inline-block",
                      getLevelStyles(log.level)
                    )}>
                      {log.level}_LOG
                    </span>
                  </div>
                  <div className="px-2">
                    <span className={cn(
                      "px-2 py-0.5 rounded text-[8px] font-black uppercase border inline-block",
                      log.source === 'hermes' ? "bg-[#FF6B00]/5 text-[#FF6B00]/60 border-[#FF6B00]/10" : "bg-white/[0.03] text-white/30 border-white/5"
                    )}>
                      {log.source}
                    </span>
                  </div>
                  <span className="font-mono text-[9px] text-white/20 truncate pr-4">{log.run_id}</span>
                  <div className="flex items-center justify-between min-w-0">
                    <span className="font-mono text-[11px] text-white/50 truncate pr-4">{log.message}</span>
                    {expandedId === log.id ? <ChevronUp className="h-3 w-3 text-white/20 shrink-0" /> : <ChevronDown className="h-3 w-3 text-white/20 shrink-0" />}
                  </div>
                </div>
                
                {expandedId === log.id && (
                  <div className="p-4 bg-[#050505] border-b border-white/[0.02] animate-in slide-in-from-top-2 duration-300">
                    <div className="bg-black border-l-2 border-[#FF6B00]/40 p-4 font-mono text-[10px] space-y-4">
                      <div className="space-y-1">
                        <span className="text-white/20 uppercase tracking-widest block">Message:</span>
                        <div className="text-white/60">{log.message}</div>
                      </div>
                      {log.detail && (
                        <div className="space-y-1">
                          <span className="text-white/20 uppercase tracking-widest block">Details:</span>
                          <div className="text-white/40 whitespace-pre-wrap">{log.detail}</div>
                        </div>
                      )}
                      <div className="pt-4 flex items-center gap-4 border-t border-white/5">
                        <div className="flex items-center gap-2">
                          <span className="text-white/20 uppercase tracking-widest">Run:</span>
                          <span className="text-[#FF6B00]/40">{log.run_id}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-white/20 uppercase tracking-widest">Level:</span>
                          <span className={getLevelStyles(log.level)}>{log.level}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-white/20 uppercase tracking-widest">Source:</span>
                          <span className="text-white/40">{log.source.toUpperCase()}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </React.Fragment>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
