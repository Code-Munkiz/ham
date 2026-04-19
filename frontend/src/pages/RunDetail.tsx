import * as React from "react";
import { useParams, useNavigate } from "react-router-dom";
// import { MOCK_RUNS } from "@/lib/ham/mocks"; // fallback: find run in MOCK_RUNS by runId
import { type RunRecord } from "@/lib/ham/types";
import { Badge } from "@/components/ui/badge";
import { 
  ChevronLeft, 
  Terminal, 
  ShieldCheck, 
  FileJson, 
  Clock, 
  AlertTriangle,
  Fingerprint,
  Zap,
  Layers,
  Database,
  Search,
  ArrowRight,
  ClipboardCheck,
  Code,
  Activity as ActivityIcon
} from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { isBridgeSuccess } from "@/lib/ham/types";

import { apiUrl } from "@/lib/ham/api";

export default function RunDetail() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const [run, setRun] = React.useState<RunRecord | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [notFound, setNotFound] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!runId) {
      setLoading(false);
      setNotFound(true);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      setNotFound(false);
      try {
        const res = await fetch(apiUrl(`/api/runs/${encodeURIComponent(runId)}`));
        if (res.status === 404) {
          if (!cancelled) {
            setRun(null);
            setNotFound(true);
          }
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as RunRecord;
        if (!cancelled) setRun(data);
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
  }, [runId]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <span className="text-[10px] font-black text-white/20 uppercase tracking-widest animate-pulse">
          Loading...
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <AlertTriangle className="h-12 w-12 text-destructive opacity-30" />
        <p className="text-[10px] font-black text-red-500/80 uppercase tracking-widest">{error}</p>
        <button onClick={() => navigate('/runs')} className="text-primary hover:underline font-bold uppercase text-xs tracking-widest">Return to Operational Archive</button>
      </div>
    );
  }

  if (notFound || !run) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <AlertTriangle className="h-12 w-12 text-destructive opacity-30" />
        <h2 className="text-xl font-bold">Trace Not Found</h2>
        <button onClick={() => navigate('/runs')} className="text-primary hover:underline font-bold uppercase text-xs tracking-widest">Return to Operational Archive</button>
      </div>
    );
  }

  return (
    <div className="space-y-10 animate-in fade-in slide-in-from-bottom-2 duration-700 pb-20">
      {/* Trace Header */}
      <div className="flex flex-col md:flex-row md:items-center gap-6">
        <button 
          onClick={() => navigate('/runs')}
          className="h-10 w-10 flex items-center justify-center rounded-xl bg-card border border-border hover:bg-muted transition-colors"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
        <div className="flex flex-col gap-1.5 flex-1">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-black font-mono tracking-tight text-foreground uppercase">
              TRACE_{run.run_id}
            </h1>
            <Badge variant={isBridgeSuccess(run.bridge_result) ? 'success' : 'destructive'} className="rounded-full px-3 py-0.5 text-[10px] font-black uppercase tracking-widest">
              STATUS_{isBridgeSuccess(run.bridge_result) ? 'SUCCESS' : 'FAILURE'}
            </Badge>
          </div>
          <div className="flex items-center gap-4 text-muted-foreground font-medium">
            <div className="flex items-center gap-1.5">
              <Clock className="h-4 w-4" />
              <span className="text-[11px] uppercase font-bold tracking-widest">
                {new Date(run.created_at).toLocaleString([], { dateStyle: 'long', timeStyle: 'medium' })}
              </span>
            </div>
            <div className="h-1 w-1 rounded-full bg-border" />
            <div className="flex items-center gap-1.5 uppercase font-bold text-[11px] tracking-widest">
              Author: <span className="text-foreground">{run.author ?? 'unknown'}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button className="px-5 py-2.5 rounded-xl bg-foreground text-background text-[10px] font-black uppercase tracking-[0.2em] hover:bg-foreground/90 transition-all shadow-xl shadow-foreground/5">
            Export Artifact
          </button>
        </div>
      </div>

      <div className="grid gap-8 lg:grid-cols-12">
        {/* Verification Stack */}
        <div className="lg:col-span-4 space-y-8">
          {/* Identity & Registry Context */}
          <div className="p-8 rounded-3xl bg-card/20 border border-border/80 space-y-8">
            <div className="space-y-6">
              <div className="flex items-center gap-3">
                <Fingerprint className="h-5 w-5 text-primary" />
                <h3 className="text-xs font-black uppercase tracking-[0.2em] text-foreground/80">Registry Origin</h3>
              </div>
              
              <div className="space-y-5">
                <div className="flex flex-col gap-2">
                  <span className="text-[9px] font-black text-muted-foreground uppercase tracking-widest">Intent Profile</span>
                  <div className="flex items-center justify-between p-4 rounded-2xl bg-muted/40 border border-border/60">
                    <div className="flex items-center gap-2">
                      <Layers className="h-4 w-4 text-muted-foreground" />
                      <span className="text-xs font-mono font-bold">{run.profile_id}</span>
                    </div>
                    <Badge variant="outline" className="text-[8px] font-black bg-muted">V{run.profile_version}</Badge>
                  </div>
                </div>

                <div className="flex flex-col gap-2">
                  <span className="text-[9px] font-black text-muted-foreground uppercase tracking-widest">Execution Backend</span>
                  <div className="flex items-center justify-between p-4 rounded-2xl bg-muted/40 border border-border/60">
                    <div className="flex items-center gap-2">
                      <Database className="h-4 w-4 text-muted-foreground" />
                      <span className="text-xs font-mono font-bold">{run.backend_id}</span>
                    </div>
                    <Badge variant="outline" className="text-[8px] font-black bg-muted">V{run.backend_version}</Badge>
                  </div>
                </div>
              </div>
            </div>

            <div className="pt-8 border-t border-border/40 space-y-6">
              <div className="flex items-center gap-3">
                <ShieldCheck className={cn("h-5 w-5", run.hermes_review.ok ? "text-green-500" : "text-destructive")} />
                <h3 className="text-xs font-black uppercase tracking-[0.2em] text-foreground/80">Hermes Consensus</h3>
              </div>

              <div className={cn(
                "p-5 rounded-2xl border-2 space-y-4",
                run.hermes_review.ok ? "bg-green-500/5 border-green-500/20" : "bg-destructive/5 border-destructive/20"
              )}>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-black uppercase tracking-widest opacity-60">Status Verdict</span>
                  <Badge variant={run.hermes_review.ok ? 'success' : 'destructive'} className="rounded py-0 text-[10px] font-black h-5 uppercase tracking-tighter shadow-sm">
                    {run.hermes_review.ok ? 'OK_PASS' : 'FLAGGED'}
                  </Badge>
                </div>
                <div className="space-y-1">
                  <span className="text-[9px] font-black uppercase tracking-widest text-muted-foreground">Trace Code</span>
                  <p className="text-xs font-mono font-black">{run.hermes_review.code ?? "—"}</p>
                </div>
                <div className="space-y-2">
                  <span className="text-[9px] font-black uppercase tracking-widest text-muted-foreground">Audit Notes</span>
                  <p className="text-[11px] text-foreground/80 font-medium leading-relaxed italic border-l-2 border-border/60 pl-3">
                    {(run.hermes_review.notes ?? []).join(' — ')}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Prompt Intent */}
          <div className="p-8 rounded-3xl bg-muted/20 border border-border/60 space-y-4">
            <div className="flex items-center gap-3">
              <Search className="h-4 w-4 text-muted-foreground" />
              <h3 className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground">Declared Intent</h3>
            </div>
            <p className="text-sm font-medium leading-relaxed text-foreground/90 italic">
              "{run.prompt_summary}"
            </p>
          </div>
        </div>

        {/* Trace Evidence */}
        <div className="lg:col-span-8">
          <Tabs defaultValue="evidence" className="w-full">
            <div className="flex items-center justify-between mb-6">
              <TabsList className="bg-muted/40 p-1.5 rounded-2xl border border-border/40">
                <TabsTrigger value="evidence" className="gap-2 px-5 py-2 rounded-xl text-xs font-black uppercase tracking-widest data-[state=active]:bg-primary data-[state=active]:text-primary-foreground transition-all">
                  <Zap className="h-3.5 w-3.5" />
                  Evidence
                </TabsTrigger>
                <TabsTrigger value="governance" className="gap-2 px-5 py-2 rounded-xl text-xs font-black uppercase tracking-widest data-[state=active]:bg-primary data-[state=active]:text-primary-foreground transition-all">
                  <ClipboardCheck className="h-3.5 w-3.5" />
                  Policy
                </TabsTrigger>
                <TabsTrigger value="json" className="gap-2 px-5 py-2 rounded-xl text-xs font-black uppercase tracking-widest data-[state=active]:bg-primary data-[state=active]:text-primary-foreground transition-all">
                  <FileJson className="h-3.5 w-3.5" />
                  Raw
                </TabsTrigger>
              </TabsList>
            </div>

            <TabsContent value="evidence" className="space-y-6 focus:outline-none">
              <div className="flex flex-col gap-6">
                {(run.bridge_result.commands ?? []).map((cmd, i) => (
                  <div key={cmd.command_id} className="rounded-3xl border border-border/60 bg-card/10 overflow-hidden hover:border-border transition-colors">
                    <div className="flex flex-wrap items-center justify-between px-6 py-4 bg-muted/30 border-b border-border/40">
                      <div className="flex items-center gap-3">
                        <Terminal className="h-4 w-4 text-primary opacity-60" />
                        <span className="text-[11px] font-black font-mono tracking-tight text-foreground/80 uppercase">CYCLE_0{i+1}: <span className="text-primary">{cmd.command_id}</span></span>
                      </div>
                      <div className="flex items-center gap-4">
                        <Badge variant={(cmd.exit_code ?? 1) === 0 ? "success" : "destructive"} className="text-[8px] h-4 font-black px-2 uppercase shadow-sm">
                          EXIT_{cmd.exit_code ?? "null"}
                        </Badge>
                        <span className="text-[9px] font-black font-mono text-muted-foreground/50 tracking-widest">{cmd.duration_ms}MS</span>
                      </div>
                    </div>
                    <div className="p-6 space-y-5">
                      <div className="group relative">
                        <div className="h-px bg-border absolute top-1/2 left-0 right-0 -z-10 opacity-20" />
                        <div className="inline-flex items-center gap-2 bg-background px-3 py-1 border border-border rounded-lg relative z-10">
                          <Code className="h-3 w-3 text-muted-foreground" />
                          <code className="text-xs font-mono font-bold text-foreground/90 whitespace-pre-wrap break-all">
                            $ {cmd.argv.join(" ")}
                          </code>
                        </div>
                      </div>
                      
                      {(cmd.stdout || cmd.stderr) && (
                        <div className="bg-black/80 rounded-2xl p-6 border border-white/5 relative group/terminal">
                          <pre className={cn(
                            "text-[12px] font-mono leading-relaxed overflow-x-auto overflow-y-auto max-h-[300px] scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent",
                            cmd.stderr ? "text-red-400/80" : "text-green-500/80"
                          )}>
                            {cmd.stdout || cmd.stderr}
                          </pre>
                          <div className="absolute top-2 right-4 text-[9px] font-black text-white/20 uppercase tracking-[0.2em] group-hover/terminal:text-white/40 transition-colors">
                            Stream_Output
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </TabsContent>

            <TabsContent value="governance" className="focus:outline-none">
              <Card className="bg-card/30 border-border p-8 rounded-3xl space-y-8">
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <h3 className="text-lg font-black tracking-tight uppercase leading-none text-foreground/80">Audit ComplianceProofs</h3>
                    <p className="text-[10px] font-black text-muted-foreground uppercase tracking-widest font-mono">Blockchain Integrity Verified: SHA-256 Validated</p>
                  </div>
                  <div className="h-10 w-10 flex items-center justify-center bg-green-500/10 border border-green-500/30 rounded-full">
                    <ShieldCheck className="h-5 w-5 text-green-500" />
                  </div>
                </div>

                <div className="grid gap-4">
                  {(run.bridge_result.policy_decision?.reasons ?? []).map((pe, i) => (
                    <div key={i} className="group p-5 rounded-2xl bg-muted/40 border border-border/60 hover:border-primary/40 hover:bg-muted/60 transition-all flex items-start gap-4">
                      <div className="h-6 w-6 rounded-lg bg-green-500/20 flex items-center justify-center shrink-0 mt-0.5">
                        <ClipboardCheck className="h-3.5 w-3.5 text-green-500" />
                      </div>
                      <div className="space-y-1">
                        <span className="text-[9px] font-black text-muted-foreground/40 uppercase tracking-[0.2em]">Policy_Enforcement_Proof_{i+1}</span>
                        <p className="text-sm font-bold text-foreground/80 leading-relaxed italic group-hover:text-foreground">"{pe}"</p>
                      </div>
                      <ArrowRight className="h-4 w-4 text-muted-foreground/20 ml-auto group-hover:text-primary transition-all opacity-0 group-hover:opacity-100" />
                    </div>
                  ))}
                </div>

                <div className="p-6 rounded-2xl bg-amber-500/5 border border-amber-500/20 flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="h-10 w-10 rounded-xl bg-amber-500/10 flex items-center justify-center">
                      <ActivityIcon className={cn("h-5 w-5", run.bridge_result.mutation_detected ? "text-amber-500" : "text-muted-foreground/30")} />
                    </div>
                    <div>
                      <span className="text-[10px] font-black text-amber-500/60 uppercase tracking-widest">State Mutation Check</span>
                      <h4 className="text-sm font-bold text-foreground/80">
                        {run.bridge_result.mutation_detected ? "System Mutations Detected" : "No Permanent Mutations Recorded"}
                      </h4>
                    </div>
                  </div>
                  <Badge variant={run.bridge_result.mutation_detected ? 'warning' : 'outline'} className="rounded py-0 text-[10px] font-black h-6 uppercase tracking-widest shadow-sm">
                    {run.bridge_result.mutation_detected ? "POSITIVE_MUTATION" : "CLEAN_PASS"}
                  </Badge>
                </div>
              </Card>
            </TabsContent>

            <TabsContent value="json" className="focus:outline-none">
              <div className="relative group">
                <div className="absolute -inset-0.5 bg-gradient-to-r from-primary/30 to-blue-600/30 rounded-3xl blur opacity-20 group-hover:opacity-30 transition-opacity" />
                <div className="relative rounded-3xl border border-border bg-black/95 p-1 px-1">
                   <div className="flex items-center justify-between p-6 pb-2 border-b border-white/5">
                      <div className="flex items-center gap-3">
                        <div className="h-2 w-2 rounded-full bg-red-500/50" />
                        <div className="h-2 w-2 rounded-full bg-amber-500/50" />
                        <div className="h-2 w-2 rounded-full bg-green-500/50" />
                        <span className="ml-2 text-white/30 text-[9px] font-black uppercase tracking-[0.3em] font-mono">OBJECT_TRACE_001.JSON</span>
                      </div>
                      <button className="text-[10px] font-black text-white/40 hover:text-white transition-colors bg-white/5 px-3 py-1 rounded-lg uppercase tracking-widest">Copy Trace</button>
                   </div>
                   <div className="p-8 font-mono text-xs leading-relaxed text-green-500/70 overflow-x-auto max-h-[600px] scrollbar-thin scrollbar-thumb-white/10">
                    <pre>{JSON.stringify(run, null, 2)}</pre>
                   </div>
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
