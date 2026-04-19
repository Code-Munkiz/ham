import * as React from "react";
import { useMemo } from "react";
import { type RunRecord, isBridgeSuccess } from "@/lib/ham/types";
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line
} from "recharts";
import { 
  Activity, 
  TrendingUp, 
  Users, 
  Zap,
  ArrowUpRight,
  ArrowDownRight,
  ShieldCheck,
  Cpu,
  History
} from "lucide-react";
const API_BASE = "http://localhost:8000";

const COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444'];

export default function Analytics() {
  const [allRuns, setAllRuns] = React.useState<RunRecord[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${API_BASE}/api/runs?limit=200`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as { runs: RunRecord[] };
        if (!cancelled) setAllRuns(data.runs ?? []);
      } catch (e) {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Request failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const totalRuns = allRuns.length;
  const successfulRuns = allRuns.filter(r => isBridgeSuccess(r.bridge_result)).length;
  const successRate = totalRuns > 0 ? (successfulRuns / totalRuns) * 100 : 0;

  const runsPerDay = useMemo(() => {
    const map = new Map<string, number>();
    allRuns.forEach(r => {
      const day = r.created_at.split('T')[0];
      map.set(day, (map.get(day) || 0) + 1);
    });
    return Array.from(map.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([date, count]) => ({ date, count }));
  }, [allRuns]);

  const profileUsage = useMemo(() => {
    const map = new Map<string, number>();
    allRuns.forEach(r => {
      map.set(r.profile_id, (map.get(r.profile_id) || 0) + 1);
    });
    return Array.from(map.entries()).map(([name, value]) => ({ name, value }));
  }, [allRuns]);

  const maxDaily = runsPerDay.length ? Math.max(...runsPerDay.map(d => d.count)) : 0;
  const maxProfile = profileUsage.length ? Math.max(...profileUsage.map(p => p.value)) : 0;

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-12">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="h-px w-8 bg-primary/40" />
            <span className="text-[10px] font-black text-primary uppercase tracking-[0.3em]">Intelligence Layer</span>
          </div>
          <h1 className="text-4xl font-black tracking-tighter uppercase italic">Operational Analytics</h1>
          <p className="text-muted-foreground font-mono text-xs mt-2 max-w-xl">
            Deep telemetry on swarm efficiency, model routing, and execution stability across the Ham network.
          </p>
        </div>
        <div className="flex gap-4">
          <div className="px-4 py-2 rounded-xl bg-white/[0.02] border border-white/5 flex flex-col items-end">
            <span className="text-[8px] font-black text-white/20 uppercase tracking-widest">Global Success</span>
            {loading ? (
              <span className="text-[10px] font-black text-white/20 uppercase tracking-widest animate-pulse">Loading...</span>
            ) : error ? (
              <span className="text-[10px] font-black text-red-500/80 uppercase tracking-widest">{error}</span>
            ) : (
              <span className="text-xl font-black text-emerald-500">{successRate.toFixed(1)}%</span>
            )}
          </div>
          <div className="px-4 py-2 rounded-xl bg-white/[0.02] border border-white/5 flex flex-col items-end">
            <span className="text-[8px] font-black text-white/20 uppercase tracking-widest">Total Volume</span>
            {loading ? (
              <span className="text-[10px] font-black text-white/20 uppercase tracking-widest animate-pulse">Loading...</span>
            ) : error ? (
              <span className="text-[10px] font-black text-red-500/80 uppercase tracking-widest">—</span>
            ) : (
              <span className="text-xl font-black">{totalRuns}</span>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 p-8 rounded-[2rem] bg-white/[0.02] border border-white/5 shadow-2xl relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-8 opacity-5 group-hover:opacity-10 transition-opacity">
            <Activity className="h-32 w-32" />
          </div>
          <div className="flex items-center justify-between mb-8">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-primary/10 text-primary">
                <TrendingUp className="h-4 w-4" />
              </div>
              <h3 className="text-sm font-black uppercase tracking-widest">Execution Velocity</h3>
            </div>
            <div className="flex gap-4 text-[10px] font-mono font-bold text-white/20 uppercase">
              <span className="flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-primary" /> Daily Runs</span>
            </div>
          </div>
          <div className="h-[300px] w-full">
            {loading ? (
              <div className="h-full flex items-center justify-center">
                <span className="text-[10px] font-black text-white/20 uppercase tracking-widest animate-pulse">Loading...</span>
              </div>
            ) : error ? (
              <div className="h-full flex items-center justify-center">
                <span className="text-[10px] font-black text-red-500/80 uppercase tracking-widest">{error}</span>
              </div>
            ) : runsPerDay.length === 0 ? (
              <div className="h-full flex items-center justify-center">
                <span className="text-[10px] font-black text-white/30 uppercase tracking-widest">No run data yet</span>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={runsPerDay}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis 
                    dataKey="date" 
                    stroke="rgba(255,255,255,0.1)" 
                    fontSize={10} 
                    tickLine={false} 
                    axisLine={false}
                    tickFormatter={(val) => val.split('-').slice(1).join('/')}
                  />
                  <YAxis 
                    stroke="rgba(255,255,255,0.1)" 
                    fontSize={10} 
                    tickLine={false} 
                    axisLine={false}
                    domain={[0, maxDaily > 0 ? Math.ceil(maxDaily * 1.2) : 1]}
                  />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#0a0a0a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', fontSize: '10px' }}
                    itemStyle={{ color: '#fff' }}
                  />
                  <Bar dataKey="count" fill="currentColor" className="text-primary fill-primary/40 hover:fill-primary transition-all duration-300" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="p-8 rounded-[2rem] bg-white/[0.02] border border-white/5 shadow-2xl flex flex-col">
          <div className="flex items-center gap-3 mb-8">
            <div className="p-2 rounded-lg bg-purple-500/10 text-purple-400">
              <Users className="h-4 w-4" />
            </div>
            <h3 className="text-sm font-black uppercase tracking-widest">Profile Load</h3>
          </div>
          <div className="flex-1 min-h-[200px] relative">
            {loading ? (
              <div className="h-full flex items-center justify-center">
                <span className="text-[10px] font-black text-white/20 uppercase tracking-widest animate-pulse">Loading...</span>
              </div>
            ) : error ? (
              <div className="h-full flex items-center justify-center">
                <span className="text-[10px] font-black text-red-500/80 uppercase tracking-widest">{error}</span>
              </div>
            ) : profileUsage.length === 0 ? (
              <div className="h-full flex items-center justify-center">
                <span className="text-[10px] font-black text-white/30 uppercase tracking-widest">No profile data</span>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={profileUsage}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={8}
                    dataKey="value"
                  >
                    {profileUsage.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} stroke="rgba(0,0,0,0.2)" />
                    ))}
                  </Pie>
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#0a0a0a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', fontSize: '10px' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
          <div className="mt-6 space-y-3">
            {profileUsage.map((p, i) => (
              <div key={p.name} className="flex items-center justify-between text-[10px] font-mono font-bold uppercase">
                <div className="flex items-center gap-2">
                  <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                  <span className="text-white/40">{p.name}</span>
                </div>
                <span>{maxProfile > 0 ? ((p.value / maxProfile) * 100).toFixed(0) : 0}% Load</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="p-8 rounded-[2rem] bg-white/[0.02] border border-white/5">
          <div className="flex items-center justify-between mb-8">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
                <ShieldCheck className="h-4 w-4" />
              </div>
              <h3 className="text-sm font-black uppercase tracking-widest">Stability Index</h3>
            </div>
            <div className="flex items-center gap-1 text-emerald-500 text-[10px] font-black">
              <ArrowUpRight className="h-3 w-3" />
              OPTIMAL
            </div>
          </div>
          <div className="h-[200px] w-full">
            {loading ? (
              <div className="h-full flex items-center justify-center">
                <span className="text-[10px] font-black text-white/20 uppercase tracking-widest animate-pulse">Loading...</span>
              </div>
            ) : error ? (
              <div className="h-full flex items-center justify-center">
                <span className="text-[10px] font-black text-red-500/80 uppercase tracking-widest">{error}</span>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={runsPerDay}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis dataKey="date" hide />
                  <YAxis hide domain={[0, 100]} />
                  <Tooltip contentStyle={{ backgroundColor: '#0a0a0a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', fontSize: '10px' }} />
                  <Line 
                    type="monotone" 
                    dataKey="count" 
                    stroke="#10b981" 
                    strokeWidth={3} 
                    dot={false}
                    strokeOpacity={0.4}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="p-8 rounded-[2rem] bg-white/[0.02] border border-white/5 flex flex-col justify-center">
          <div className="grid grid-cols-2 gap-4">
            <div className="p-6 rounded-2xl bg-white/[0.03] border border-white/5">
              <Cpu className="h-5 w-5 text-blue-400 mb-4 opacity-50" />
              <div className="text-[8px] font-black text-white/20 uppercase tracking-widest mb-1">Avg Latency</div>
              <div className="text-2xl font-black italic">42ms</div>
            </div>
            <div className="p-6 rounded-2xl bg-white/[0.03] border border-white/5">
              <Zap className="h-5 w-5 text-amber-400 mb-4 opacity-50" />
              <div className="text-[8px] font-black text-white/20 uppercase tracking-widest mb-1">Token Velocity</div>
              <div className="text-2xl font-black italic">1.2k/s</div>
            </div>
            <div className="col-span-2 p-6 rounded-2xl bg-primary/5 border border-primary/10 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <History className="h-6 w-6 text-primary" />
                <div>
                  <div className="text-[10px] font-black uppercase tracking-widest text-primary">Historical Peak</div>
                  <div className="text-xs font-mono text-white/40">Concurrent execution nodes reached maximum capacity on {runsPerDay.length ? runsPerDay[runsPerDay.length - 1].date : "—"}</div>
                </div>
              </div>
              <ArrowDownRight className="h-5 w-5 text-white/10" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
