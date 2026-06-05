const services = [
  {
    title: "AI Workflow Design",
    detail: "Map high-leverage automations, approval paths, and guardrails for ops teams.",
    icon: "workflow",
  },
  {
    title: "Custom Agents",
    detail: "Ship reliable assistants with review loops, evals, and human handoff.",
    icon: "agents",
  },
  {
    title: "Integration Layer",
    detail: "Connect CRMs, inboxes, data warehouses, and internal tools safely.",
    icon: "integration",
  },
];

const steps = [
  { label: "Discover", detail: "Interview stakeholders, audit systems, and define success metrics." },
  { label: "Prototype", detail: "Validate UX and automation paths in days, not months." },
  { label: "Launch", detail: "Harden, monitor, document, and train your team." },
];

const stats = [
  { value: "48h", label: "Typical prototype window" },
  { value: "3x", label: "Faster ops handoffs" },
  { value: "99.9%", label: "Uptime on shipped flows" },
];

function ServiceIcon({ name }: { name: string }) {
  if (name === "workflow") {
    return (
      <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M4 7h6l2 3h8" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M4 17h16" strokeLinecap="round" />
        <circle cx="7" cy="7" r="2" />
        <circle cx="17" cy="17" r="2" />
      </svg>
    );
  }
  if (name === "agents") {
    return (
      <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.8">
        <rect x="5" y="8" width="14" height="10" rx="2" />
        <path d="M9 8V6a3 3 0 0 1 6 0v2" strokeLinecap="round" />
        <path d="M9 14h.01M15 14h.01" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M8 12h8M12 8v8" strokeLinecap="round" />
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  );
}

export default function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-40 border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-sky-400 to-indigo-500 text-sm font-bold text-slate-950 shadow-lg shadow-sky-500/20">
              NL
            </span>
            <span className="text-sm font-semibold tracking-wide text-white">Northline Studio</span>
          </div>
          <nav className="hidden gap-8 text-sm text-slate-300 md:flex">
            <a className="transition hover:text-white" href="#services">
              Services
            </a>
            <a className="transition hover:text-white" href="#process">
              Process
            </a>
            <a className="transition hover:text-white" href="#contact">
              Contact
            </a>
          </nav>
          <button
            type="button"
            className="rounded-full bg-sky-400 px-4 py-2 text-sm font-semibold text-slate-950 shadow-lg shadow-sky-500/25 transition hover:bg-sky-300"
          >
            Book intro
          </button>
        </div>
      </header>

      <main>
        <section
          data-ham-section="hero"
          className="relative overflow-hidden border-b border-slate-800/60"
        >
          <div className="pointer-events-none absolute -left-24 top-10 h-72 w-72 rounded-full bg-sky-500/20 blur-3xl" />
          <div className="pointer-events-none absolute -right-16 top-32 h-80 w-80 rounded-full bg-indigo-500/15 blur-3xl" />
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-sky-500/10 via-slate-950 to-indigo-600/10" />
          <div className="relative mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-24 lg:px-8 lg:py-28">
            <span className="inline-flex items-center rounded-full border border-sky-400/30 bg-sky-400/10 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-sky-200">
              AI automation agency
            </span>
            <h1 className="mt-6 max-w-4xl text-4xl font-bold tracking-tight text-white sm:text-5xl lg:text-6xl lg:leading-[1.05]">
              Build automation experiences that look{" "}
              <span className="bg-gradient-to-r from-sky-300 via-cyan-200 to-indigo-300 bg-clip-text text-transparent">
                production-ready
              </span>{" "}
              on day one.
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-relaxed text-slate-300 sm:text-xl">
              We design landing pages, internal tools, and agent workflows with crisp hierarchy,
              responsive layouts, and guardrails your clients can trust.
            </p>
            <div className="mt-10 flex flex-col gap-3 sm:flex-row sm:items-center">
              <button
                type="button"
                className="rounded-xl bg-sky-400 px-6 py-3.5 text-base font-semibold text-slate-950 shadow-xl shadow-sky-500/30 transition hover:bg-sky-300"
              >
                Start a project
              </button>
              <button
                type="button"
                className="rounded-xl border border-slate-700 bg-slate-900/70 px-6 py-3.5 text-base font-semibold text-slate-100 shadow-lg shadow-black/20 transition hover:border-slate-500 hover:bg-slate-900"
              >
                View capabilities
              </button>
            </div>
            <dl className="mt-14 grid gap-6 border-t border-slate-800/80 pt-10 sm:grid-cols-3">
              {stats.map((item) => (
                <div key={item.label} className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-5">
                  <dt className="text-3xl font-bold text-white">{item.value}</dt>
                  <dd className="mt-2 text-sm text-slate-400">{item.label}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <section data-ham-section="services" id="services" className="py-16 sm:py-24">
          <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
            <p className="text-sm font-semibold uppercase tracking-[0.16em] text-sky-300">Services</p>
            <h2 className="mt-3 text-3xl font-bold text-white sm:text-4xl">
              Everything you need to ship credible AI automation
            </h2>
            <p className="mt-4 max-w-2xl text-base leading-relaxed text-slate-400">
              Structured cards, strong contrast, and responsive grids — ready for Hermes to remix
              with your brand voice.
            </p>
            <div className="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {services.map((item) => (
                <article
                  key={item.title}
                  className="group rounded-2xl border border-slate-800 bg-slate-900/70 p-6 shadow-xl shadow-black/20 transition hover:-translate-y-0.5 hover:border-sky-500/40 hover:shadow-sky-500/10"
                >
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-sky-400/10 text-sky-300 ring-1 ring-sky-400/20">
                    <ServiceIcon name={item.icon} />
                  </div>
                  <h3 className="mt-5 text-lg font-semibold text-white">{item.title}</h3>
                  <p className="mt-3 text-sm leading-relaxed text-slate-300">{item.detail}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section
          data-ham-section="process"
          id="process"
          className="border-y border-slate-800/70 bg-slate-900/40 py-16 sm:py-24"
        >
          <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
            <p className="text-sm font-semibold uppercase tracking-[0.16em] text-sky-300">Process</p>
            <h2 className="mt-3 text-3xl font-bold text-white sm:text-4xl">From discovery to launch</h2>
            <ol className="mt-12 grid gap-6 md:grid-cols-3">
              {steps.map((step, index) => (
                <li
                  key={step.label}
                  className="relative rounded-2xl border border-slate-700/80 bg-slate-950/60 p-6 shadow-lg shadow-black/10"
                >
                  <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-sky-400/15 text-sm font-bold text-sky-200 ring-1 ring-sky-400/30">
                    {index + 1}
                  </span>
                  <h3 className="mt-4 text-xl font-semibold text-white">{step.label}</h3>
                  <p className="mt-3 text-sm leading-relaxed text-slate-300">{step.detail}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section data-ham-section="testimonial" className="py-16 sm:py-24">
          <div className="mx-auto max-w-4xl px-4 sm:px-6">
            <figure className="rounded-3xl border border-slate-800 bg-gradient-to-b from-slate-900 to-slate-950 p-8 shadow-2xl shadow-black/30 sm:p-10">
              <div className="flex items-center justify-center gap-1 text-sky-300">
                {Array.from({ length: 5 }).map((_, i) => (
                  <span key={i} className="text-lg leading-none">
                    ★
                  </span>
                ))}
              </div>
              <blockquote className="mt-6 text-center text-xl leading-relaxed text-slate-200 sm:text-2xl">
                “Northline delivered a launch-ready site and automation playbook in two weeks — our
                sales team finally had something polished to share.”
              </blockquote>
              <figcaption className="mt-8 flex items-center justify-center gap-4">
                <span className="flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br from-sky-400 to-indigo-500 text-sm font-bold text-slate-950">
                  JL
                </span>
                <div className="text-left">
                  <p className="font-semibold text-white">Jordan Lee</p>
                  <p className="text-sm text-slate-400">COO, Relay Ops</p>
                </div>
              </figcaption>
            </figure>
          </div>
        </section>

        <section
          data-ham-section="cta"
          id="contact"
          className="border-t border-slate-800 bg-slate-950 py-16 sm:py-24"
        >
          <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
            <div className="rounded-3xl border border-slate-700/80 bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 p-8 shadow-2xl shadow-black/30 sm:p-10 lg:flex lg:items-center lg:justify-between lg:gap-10">
              <div className="max-w-2xl">
                <p className="text-sm font-semibold uppercase tracking-[0.16em] text-sky-300">
                  Ready to build?
                </p>
                <h2 className="mt-3 text-3xl font-bold text-white sm:text-4xl">
                  Let&apos;s design your next automation experience
                </h2>
                <p className="mt-4 text-base leading-relaxed text-slate-300">
                  Tell us about your agency, product, or internal ops team. We&apos;ll respond with a
                  scoped plan and timeline.
                </p>
              </div>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row lg:mt-0 lg:flex-col xl:flex-row">
                <button
                  type="button"
                  className="rounded-xl bg-white px-6 py-3.5 text-base font-semibold text-slate-950 shadow-lg transition hover:bg-slate-100"
                >
                  Schedule a call
                </button>
                <a
                  href="mailto:hello@example.com"
                  className="rounded-xl border border-slate-600 px-6 py-3.5 text-center text-base font-semibold text-slate-100 transition hover:border-slate-400 hover:bg-slate-900"
                >
                  Email the team
                </a>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
