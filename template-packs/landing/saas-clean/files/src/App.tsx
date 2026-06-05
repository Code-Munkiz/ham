const services = [
  { title: "AI Workflow Design", detail: "Map high-leverage automations for ops teams." },
  { title: "Custom Agents", detail: "Ship reliable assistants with guardrails and review loops." },
  { title: "Integration Layer", detail: "Connect CRMs, inboxes, and data warehouses safely." },
];

const steps = [
  { label: "Discover", detail: "Interview stakeholders and audit systems." },
  { label: "Prototype", detail: "Validate UX and automation paths in days." },
  { label: "Launch", detail: "Harden, monitor, and train your team." },
];

export default function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800/80 bg-slate-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <span className="text-sm font-semibold tracking-wide text-sky-300">Northline Studio</span>
          <nav className="hidden gap-6 text-sm text-slate-300 md:flex">
            <a className="hover:text-white" href="#services">
              Services
            </a>
            <a className="hover:text-white" href="#process">
              Process
            </a>
            <a className="hover:text-white" href="#contact">
              Contact
            </a>
          </nav>
          <button
            type="button"
            className="rounded-full bg-sky-400 px-4 py-2 text-sm font-semibold text-slate-950 shadow-lg shadow-sky-500/20 hover:bg-sky-300"
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
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-sky-500/10 via-transparent to-indigo-500/10" />
          <div className="relative mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-24 lg:px-8">
            <p className="text-sm font-medium uppercase tracking-[0.2em] text-sky-300">
              AI automation agency
            </p>
            <h1 className="mt-4 max-w-3xl font-display text-4xl font-bold tracking-tight text-white sm:text-5xl lg:text-6xl">
              Ship polished automation experiences your clients can trust.
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-relaxed text-slate-300">
              We design landing pages, internal tools, and agent workflows with crisp visual
              hierarchy, responsive layouts, and production-ready guardrails.
            </p>
            <div className="mt-10 flex flex-col gap-3 sm:flex-row">
              <button
                type="button"
                className="rounded-xl bg-sky-400 px-6 py-3 text-base font-semibold text-slate-950 shadow-xl shadow-sky-500/25 hover:bg-sky-300"
              >
                Start a project
              </button>
              <button
                type="button"
                className="rounded-xl border border-slate-700 bg-slate-900/60 px-6 py-3 text-base font-semibold text-slate-100 hover:border-slate-500"
              >
                View capabilities
              </button>
            </div>
          </div>
        </section>

        <section data-ham-section="services" id="services" className="py-16 sm:py-20">
          <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
            <h2 className="text-3xl font-bold text-white">Services</h2>
            <p className="mt-3 max-w-2xl text-slate-400">
              Structured cards with contrast, spacing, and responsive grids.
            </p>
            <div className="mt-10 grid gap-6 md:grid-cols-3">
              {services.map((item) => (
                <article
                  key={item.title}
                  className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6 shadow-xl shadow-black/20"
                >
                  <h3 className="text-lg font-semibold text-white">{item.title}</h3>
                  <p className="mt-3 text-sm leading-relaxed text-slate-300">{item.detail}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section data-ham-section="process" id="process" className="border-y border-slate-800/70 bg-slate-900/40 py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
            <h2 className="text-3xl font-bold text-white">Process</h2>
            <ol className="mt-10 grid gap-6 md:grid-cols-3">
              {steps.map((step, index) => (
                <li
                  key={step.label}
                  className="rounded-2xl border border-slate-700/80 bg-slate-950/60 p-6"
                >
                  <span className="text-sm font-semibold text-sky-300">Step {index + 1}</span>
                  <h3 className="mt-2 text-xl font-semibold text-white">{step.label}</h3>
                  <p className="mt-3 text-sm text-slate-300">{step.detail}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section data-ham-section="testimonial" className="py-16 sm:py-20">
          <div className="mx-auto max-w-4xl px-4 text-center sm:px-6">
            <figure className="rounded-3xl border border-slate-800 bg-gradient-to-b from-slate-900 to-slate-950 p-10 shadow-2xl">
              <blockquote className="text-xl leading-relaxed text-slate-200 sm:text-2xl">
                “The team delivered a launch-ready site and automation playbook in two weeks.”
              </blockquote>
              <figcaption className="mt-6 text-sm text-slate-400">
                Jordan Lee — COO, Relay Ops
              </figcaption>
            </figure>
          </div>
        </section>

        <section
          data-ham-section="cta"
          id="contact"
          className="border-t border-slate-800 bg-slate-900/50 py-16"
        >
          <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-6 px-4 sm:flex-row sm:items-center sm:px-6 lg:px-8">
            <div>
              <h2 className="text-3xl font-bold text-white">Ready to build?</h2>
              <p className="mt-2 text-slate-300">Tell us about your agency or automation shop.</p>
            </div>
            <button
              type="button"
              className="rounded-xl bg-white px-6 py-3 text-base font-semibold text-slate-950 shadow-lg hover:bg-slate-100"
            >
              Schedule a call
            </button>
          </div>
        </section>
      </main>
    </div>
  );
}
