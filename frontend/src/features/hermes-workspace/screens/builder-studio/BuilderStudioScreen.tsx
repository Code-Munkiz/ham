import * as React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Plus, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useHamWorkspace } from "@/lib/ham/HamWorkspaceContext";
import {
  WorkspaceSurfaceHeader,
  WorkspaceSurfaceStateCard,
} from "../../components/workspaceSurfaceChrome";
import {
  builderStudioAdapter,
  adapterErrorMessage,
  type AdapterError,
  type BuilderPublic,
} from "../../adapters/builderStudioAdapter";
import { BuilderCard } from "./BuilderCard";
import { CreateBuilderWizard } from "./CreateBuilderWizard";
import { BuilderDetailDrawer } from "./BuilderDetailDrawer";
import { BuilderTechnicalDetailsDrawer } from "./BuilderTechnicalDetailsDrawer";

const FEATURE_DISABLED_COPY = "Builder Studio is being prepared — check back soon.";

export function BuilderStudioScreen() {
  const ctx = useHamWorkspace();
  const navigate = useNavigate();
  const params = useParams<{ builderId?: string }>();

  const workspaceId = ctx.state.status === "ready" ? ctx.state.activeWorkspaceId?.trim() || "" : "";

  const [builders, setBuilders] = React.useState<BuilderPublic[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<AdapterError | null>(null);
  const [wizardOpen, setWizardOpen] = React.useState(false);
  const [selected, setSelected] = React.useState<BuilderPublic | null>(null);
  const [technicalFor, setTechnicalFor] = React.useState<BuilderPublic | null>(null);

  const refresh = React.useCallback(async () => {
    if (!workspaceId) {
      setBuilders([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    const result = await builderStudioAdapter.list(workspaceId);
    setLoading(false);
    if (result.error) {
      setError(result.error);
      setBuilders([]);
      return;
    }
    setBuilders(result.builders);
  }, [workspaceId]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  React.useEffect(() => {
    if (!params.builderId) {
      setSelected((current) => (current ? null : current));
      return;
    }
    if (!builders.length) return;
    const found = builders.find((b) => b.builder_id === params.builderId) ?? null;
    setSelected(found);
  }, [params.builderId, builders]);

  const isOperator = false;

  const closeSelected = () => {
    setSelected(null);
    if (params.builderId) navigate("/workspace/builder-studio");
  };

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col gap-3 p-3 md:p-4">
      <WorkspaceSurfaceHeader
        eyebrow="Workspace"
        title="Builder Studio"
        subtitle="Reusable builder profiles HAM can pick when they match what you're working on."
        actions={
          <>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => void refresh()}
              disabled={loading}
              className="h-8 gap-1"
            >
              <RefreshCw className={loading ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />
              Refresh
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={() => setWizardOpen(true)}
              disabled={!workspaceId || error?.kind === "feature_disabled"}
              className="h-8 gap-1"
            >
              <Plus className="h-3.5 w-3.5" />
              Create builder
            </Button>
          </>
        }
      />

      {error?.kind === "feature_disabled" ? (
        <WorkspaceSurfaceStateCard
          title="Builder Studio"
          description={FEATURE_DISABLED_COPY}
          tone="amber"
        />
      ) : null}

      {error && error.kind !== "feature_disabled" ? (
        <WorkspaceSurfaceStateCard
          title="Couldn't load Builder Studio"
          description={adapterErrorMessage(error)}
          tone="amber"
          primaryAction={
            <Button type="button" size="sm" variant="secondary" onClick={() => void refresh()}>
              Retry
            </Button>
          }
        />
      ) : null}

      {loading && !error ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="h-[180px] animate-pulse rounded-2xl border border-white/10 bg-black/20"
            />
          ))}
        </div>
      ) : null}

      {!loading && !error && builders.length === 0 ? (
        <WorkspaceSurfaceStateCard
          title="No custom builders yet"
          description="Create one to give HAM a reusable recipe for what you're building."
          primaryAction={
            <Button type="button" size="sm" onClick={() => setWizardOpen(true)}>
              Create builder
            </Button>
          }
        />
      ) : null}

      {!loading && !error && builders.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {builders.map((b) => (
            <BuilderCard
              key={b.builder_id}
              builder={b}
              isOperator={isOperator}
              onOpen={() => {
                setSelected(b);
                navigate(`/workspace/builder-studio/${encodeURIComponent(b.builder_id)}`);
              }}
              onOpenTechnical={() => setTechnicalFor(b)}
            />
          ))}
        </div>
      ) : null}

      {wizardOpen && workspaceId ? (
        <CreateBuilderWizard
          workspaceId={workspaceId}
          onClose={() => setWizardOpen(false)}
          onCreated={() => {
            setWizardOpen(false);
            void refresh();
          }}
        />
      ) : null}

      {selected ? (
        <BuilderDetailDrawer
          builder={selected}
          workspaceId={workspaceId}
          isOperator={isOperator}
          onClose={closeSelected}
          onChanged={() => void refresh()}
          onOpenTechnical={() => setTechnicalFor(selected)}
        />
      ) : null}

      {technicalFor ? (
        <BuilderTechnicalDetailsDrawer
          builder={technicalFor}
          isOperator={isOperator}
          onClose={() => setTechnicalFor(null)}
        />
      ) : null}
    </div>
  );
}
