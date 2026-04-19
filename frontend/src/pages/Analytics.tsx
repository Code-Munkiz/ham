import { useState, useMemo } from 'react';
import { BarChart, Bar, PieChart, Pie, Cell, ResponsiveContainer, XAxis, YAxis, Tooltip, Legend, CartesianGrid } from 'recharts';
import { BarChart2, TrendingUp, TrendingDown, Clock, Users as UsersIcon, ShieldCheck as ShieldCheckIcon, Calendar } from 'lucide-react';
import { cn } from '@/lib/utils';
import { type RunRecord, isBridgeSuccess } from '@/lib/ham/types';

// Mock Data Generation
const AUTHORS = ['aaron', 'system', 'devops'];
const PROFILES = ['inspect_repo_v1', 'review_diff_v1', 'audit_security_v2', 'generate_docs_v1', 'kernel_sync_v1'];
const BACKENDS = ['local-droid-v0', 'cloud-bridge-v1', 'enterprise-cluster-v2'];

const generateMockData = (days: number): RunRecord[] => {
  const records: RunRecord[] = [];
  const now = new Date();
  
  for (let i = 0; i < 60; i++) {
    const date = new Date(now);
    date.setDate(now.getDate() - Math.floor(Math.random() * days));
    date.setHours(Math.floor(Math.random() * 24), Math.floor(Math.random() * 60));
    
    const runId = `run-${Math.random().toString(36).substring(2, 8)}${Math.random().toString(36).substring(2, 8)}`;
    const ok = Math.random() > 0.15;
    const reviewOk = ok ? Math.random() > 0.1 : Math.random() > 0.6;
    const iso = date.toISOString();

    records.push({
      run_id: runId,
      created_at: iso,
      profile_id: PROFILES[Math.floor(Math.random() * PROFILES.length)],
      profile_version: '1.0.0',
      backend_id: BACKENDS[Math.floor(Math.random() * BACKENDS.length)],
      backend_version: '1.0.0',
      prompt_summary: 'Synthetic analytics row',
      author: AUTHORS[Math.floor(Math.random() * AUTHORS.length)],
      bridge_result: {
        intent_id: `intent-${runId}`,
        request_id: `request-${runId}`,
        run_id: runId,
        status: ok ? 'executed' : 'failed',
        policy_decision: {
          accepted: ok,
          reasons: ok ? [] : ['synthetic failure'],
          policy_version: 'bridge-v0',
        },
        started_at: iso,
        ended_at: iso,
        duration_ms: 100,
        commands: [],
        summary: ok ? 'executed' : 'failed',
        mutation_detected: Math.random() > 0.5,
        artifacts: [],
      },
      hermes_review: {
        ok: reviewOk,
        notes: reviewOk ? ['Validation passed'] : ['Security policy violation', 'Non-deterministic output detected']
      }
    });
  }
  return records.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
};

export default function Analytics() {
  const [range, setRange] = useState<7 | 14 | 30>(14);
  const data = useMemo(() => generateMockData(range), [range]);

  // Derived Stats
  const totalRuns = data.length;
  const successRate = Math.round((data.filter(r => isBridgeSuccess(r.bridge_result)).length / totalRuns) * 100);
  const avgRunsPerDay = (totalRuns / range).toFixed(1);
  const activeAuthors = new Set(data.map(r => r.author)).size;

  // Chart Data: Runs Per Day
  const chartData = useMemo(() => {
    const days: Record<string, number> = {};
    const now = new Date();
    for (let i = range - 1; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(now.getDate() - i);
      days[d.toISOString().split('T')[0]] = 0;
    }
    
    data.forEach(r => {
      const date = r.created_at.split('T')[0];
      if (days[date] !== undefined) days[date]++;
    });

    return Object.entries(days).map(([date, count]) => ({
      date: date.substring(5), // MM-DD
      count,
    }));
  }, [data, range]);

  // Chart Data: Outcome
  const outcomeData = [
    { name: 'SUCCESS', value: data.filter(r => isBridgeSuccess(r.bridge_result)).length },
    { name: 'FAILED', value: data.filter(r => !isBridgeSuccess(r.bridge_result)).length },
  ];

  // Profile Usage Rankings
  const profileUsage = useMemo(() => {
    const counts: Record<string, number> = {};
    data.forEach(r => counts[r.profile_id] = (counts[r.profile_id] || 0) + 1);
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([name, count]) => ({ name, count }));
  }, [data]);

  const maxProfileCount = Math.max(...profileUsage.map(p => p.count));

  const lastRuns = data.slice(0, 10);

  return (
    <div className="h-full flex flex-col bg-[#050505] font-sans overflow-y-auto">
      {/* Grid Pattern */}
      <div 
        className="fixed inset-0 pointer-events-none opacity-[0.02]" 
        style={{ backgroundImage: 'linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)', backgroundSize: '64px 64px' }} 
      />

      <div className="p-8 pb-20 space-y-12 max-w-6xl mx-auto w-full animate-in fade-in duration-700 relative z-10">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 pb-8 border-b border-white/10">
          <div className="flex items-center gap-4">
            <div className="bg-[#FF6B00]/10 border border-[#FF6B00]/20 rounded p-2">
              <BarChart2 className="h-6 w-6 text-[#FF6B00]" />
            </div>
            <div>
              <h1 className="text-4xl font-black text-white italic tracking-tighter uppercase leading-none">
                Run <span className="text-[#FF6B00] not-italic">Analytics</span>
              </h1>
              <span className="mt-2 block text-[10px] font-black uppercase tracking-[0.3em] text-white/60">Global Directive Metrics</span>
            </div>
          </div>

          <div className="flex items-center bg-[#0a0a0a] rounded border border-white/5 p-1">
            {([7, 14, 30] as const).map((r) => (
              <button
                key={r}
                onClick={() => setRange(r)}
                className={cn(
                  "px-4 py-1.5 text-[10px] font-black uppercase tracking-widest rounded transition-all",
                  range === r ? "bg-[#FF6B00] text-black shadow-[0_0_12px_#FF6B00]" : "text-white/30 hover:text-white"
                )}
              >
                {r}D
              </button>
            ))}
          </div>
        </div>

        {/* Stats Row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: 'Total Runs', value: totalRuns, icon: BarChart2, delta: '+12%', pos: true },
            { label: 'Success Rate', value: `${successRate}%`, icon: ShieldCheckIcon, delta: '+2.4%', pos: true },
            { label: 'Avg Runs / Day', value: avgRunsPerDay, icon: Clock, delta: '-0.5%', pos: false },
            { label: 'Active Authors', value: activeAuthors, icon: UsersIcon, delta: '0', pos: null },
          ].map((stat, i) => (
            <div key={i} className="bg-[#0a0a0a] border border-white/5 rounded-xl p-6 relative overflow-hidden group">
              <div className="absolute top-0 left-0 bottom-0 w-1 bg-[#FF6B00] opacity-0 group-hover:opacity-100 transition-opacity" />
              <div className="flex flex-col gap-1 relative z-10">
                <span className="text-[10px] font-black uppercase tracking-[0.3em] text-white/40">{stat.label}</span>
                <div className="flex items-end justify-between gap-2 mt-2">
                  <span className="text-3xl font-black text-white tracking-tighter">{stat.value}</span>
                  {stat.pos !== null && (
                    <div className={cn(
                      "flex items-center gap-1 px-1.5 py-0.5 rounded-[4px] text-[10px] font-black italic",
                      stat.pos ? "bg-green-500/10 text-green-500" : "bg-red-500/10 text-red-500"
                    )}>
                      {stat.pos ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                      {stat.delta}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Charts Section */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Runs Per Day */}
          <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-8 space-y-6">
            <h4 className="text-[10px] font-black uppercase tracking-[0.3em] text-white/60">Runs Per Day</h4>
            <div className="h-[300px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid vertical={false} stroke="#ffffff" strokeOpacity={0.05} />
                  <XAxis 
                    dataKey="date" 
                    axisLine={false} 
                    tickLine={false} 
                    tick={{ fill: '#ffffff66', fontSize: 10, fontWeight: 900 }}
                  />
                  <YAxis 
                    axisLine={false} 
                    tickLine={false} 
                    tick={{ fill: '#ffffff66', fontSize: 10, fontWeight: 900 }}
                  />
                  <Tooltip 
                    cursor={{ fill: '#ffffff05' }}
                    contentStyle={{ backgroundColor: '#0a0a0a', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '8px' }}
                    itemStyle={{ color: '#FF6B00', fontSize: '11px', fontWeight: 'bold', textTransform: 'uppercase' }}
                    labelStyle={{ color: 'rgba(255,255,255,0.4)', fontSize: '10px', marginBottom: '4px', textTransform: 'uppercase' }}
                  />
                  <Bar 
                    dataKey="count" 
                    fill="#FF6B00" 
                    radius={[4, 4, 0, 0]}
                    activeBar={{ fill: '#FF6B00', filter: 'drop-shadow(0 0 8px #FF6B0066)' }}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Outcome Breakdown */}
          <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-8 space-y-6 flex flex-col">
            <h4 className="text-[10px] font-black uppercase tracking-[0.3em] text-white/60">Outcome Breakdown</h4>
            <div className="h-[300px] w-full flex-1 relative flex items-center justify-center">
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none flex-col">
                <span className="text-4xl font-black text-white italic pr-1">{successRate}%</span>
                <span className="text-[8px] font-black uppercase tracking-widest text-white/20">Success rate</span>
              </div>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={outcomeData}
                    cx="50%"
                    cy="50%"
                    innerRadius={80}
                    outerRadius={110}
                    paddingAngle={5}
                    dataKey="value"
                    stroke="none"
                  >
                    <Cell fill="#FF6B00" />
                    <Cell fill="#ef4444" />
                  </Pie>
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#0a0a0a', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '8px' }}
                    itemStyle={{ fontSize: '11px', fontWeight: 'bold' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex justify-center gap-8 border-t border-white/5 pt-6">
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-[#FF6B00]" />
                <span className="text-[8px] font-black uppercase tracking-widest text-white/60">SUCCESSFUL RUNS</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-[#ef4444]" />
                <span className="text-[8px] font-black uppercase tracking-widest text-white/60">FAILED RUNS</span>
              </div>
            </div>
          </div>
        </div>

        {/* Profile Usage */}
        <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-8 space-y-6">
          <h4 className="text-[10px] font-black uppercase tracking-[0.3em] text-white/60">Profile Usage Ranking</h4>
          <div className="space-y-4">
            {profileUsage.map((profile, i) => (
              <div key={i} className="space-y-2">
                <div className="flex justify-between items-end">
                  <span className="text-[11px] font-bold text-white uppercase tracking-widest">{profile.name}</span>
                  <span className="text-[11px] font-black text-[#FF6B00]">{profile.count} missions</span>
                </div>
                <div className="h-2 bg-white/5 rounded-full overflow-hidden border border-white/5">
                  <div 
                    className="h-full bg-gradient-to-r from-[#FF6B00]/40 to-[#FF6B00] shadow-[0_0_12px_#FF6B0033]" 
                    style={{ width: `${(profile.count / maxProfileCount) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* History Table */}
        <div className="space-y-6">
          <h4 className="text-[10px] font-black uppercase tracking-[0.3em] text-white/60">Recent Run History</h4>
          <div className="bg-[#0a0a0a] border border-white/5 rounded-xl overflow-hidden">
            <div className="grid grid-cols-[1fr_2fr_1.5fr_1fr_1fr_1fr] p-4 border-b border-white/10 bg-[#0d0d0d]">
              <span className="text-[9px] font-black uppercase tracking-widest text-white/30">Timestamp</span>
              <span className="text-[9px] font-black uppercase tracking-widest text-white/30">Run ID</span>
              <span className="text-[9px] font-black uppercase tracking-widest text-white/30">Profile</span>
              <span className="text-[9px] font-black uppercase tracking-widest text-white/30">Author</span>
              <span className="text-[9px] font-black uppercase tracking-widest text-white/30 text-center">Outcome</span>
              <span className="text-[9px] font-black uppercase tracking-widest text-white/30 text-center">Review</span>
            </div>
            <div className="divide-y divide-white/[0.02]">
              {lastRuns.map((run) => (
                <div key={run.run_id} className="grid grid-cols-[1fr_2fr_1.5fr_1fr_1fr_1fr] p-4 bg-[#080808] hover:bg-white/[0.04] transition-colors items-center">
                  <span className="font-mono text-[10px] text-white/30">{new Date(run.created_at).toLocaleString().split(', ')[1]}</span>
                  <span className="font-mono text-[9px] text-white/20 truncate pr-4">{run.run_id}</span>
                  <span className="text-[11px] font-bold text-white/60 uppercase tracking-widest truncate pr-4">{run.profile_id}</span>
                  <span className="text-[11px] font-bold text-white/40 uppercase tracking-widest">{run.author ?? 'unknown'}</span>
                  <div className="flex justify-center">
                    <span className={cn(
                      "px-2 py-0.5 rounded text-[8px] font-black uppercase",
                      isBridgeSuccess(run.bridge_result) ? "text-green-500 bg-green-500/10" : "text-red-500 bg-red-500/10"
                    )}>
                      {isBridgeSuccess(run.bridge_result) ? 'OK' : 'FAIL'}
                    </span>
                  </div>
                  <div className="flex justify-center">
                    <span className={cn(
                      "px-2 py-0.5 rounded text-[8px] font-black uppercase",
                      run.hermes_review.ok ? "text-green-500 bg-green-500/10" : "text-red-500 bg-red-500/10"
                    )}>
                      {run.hermes_review.ok ? 'PASS' : 'FAIL'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
