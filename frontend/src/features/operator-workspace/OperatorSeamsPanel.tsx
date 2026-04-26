const RESERVED_SEAMS = [
  {
    title: "Memory Heist / Context Preview",
    detail: "Reserved seam only in 1A.1. Full wiring lands later.",
  },
  {
    title: "Mission Context Bundle",
    detail: "Cloud Agent context packaging placeholder.",
  },
  {
    title: "Standing Instructions",
    detail: "Settings-aware context review placeholder.",
  },
  {
    title: "SWARM / Sub-agent Orchestration",
    detail: "Contract-preserving seam. No new runtime logic in 1A.1.",
  },
];

export function OperatorSeamsPanel() {
  return (
    <section className="rounded-2xl border border-white/10 bg-[#0f1520]/70 p-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.13em] text-white/50">
        Reserved seams
      </p>
      <div className="mt-2 space-y-2">
        {RESERVED_SEAMS.map((seam) => (
          <article
            key={seam.title}
            className="rounded-xl border border-white/10 bg-black/15 px-2.5 py-2"
          >
            <p className="text-xs font-medium text-white">{seam.title}</p>
            <p className="text-[11px] text-white/45">{seam.detail}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

