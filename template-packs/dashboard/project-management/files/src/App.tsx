const stats = [
  { label: "Active projects", value: "12", delta: "+2 this week" },
  { label: "On track", value: "9", delta: "75% healthy" },
  { label: "At risk", value: "3", delta: "Needs review" },
];

const activity = [
  { time: "10:24", text: "Design sync notes uploaded to Atlas roadmap." },
  { time: "09:10", text: "QA sign-off recorded for mobile onboarding." },
  { time: "Yesterday", text: "Sprint 18 scope locked with product." },
];

const workload = [
  { name: "Maya Chen", load: "6 tasks", status: "Balanced" },
  { name: "Alex Rivera", load: "9 tasks", status: "Heavy" },
  { name: "Sam Okonkwo", load: "4 tasks", status: "Light" },
];

const rows = [
  { project: "Atlas Mobile", owner: "Maya", status: "On track", due: "Jun 12" },
  { project: "Billing Revamp", owner: "Alex", status: "At risk", due: "Jun 08" },
  { project: "Support Copilot", owner: "Sam", status: "On track", due: "Jun 20" },
];

export default function App() {
  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <header className="border-b border-slate-200 bg-white shadow-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">
              Workbench
            </p>
            <h1 className="text-xl font-bold text-slate-900">Project command center</h1>
          </div>
          <button
            type="button"
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-md hover:bg-indigo-500"
          >
            New project
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
        <section data-ham-section="overview" className="grid gap-4 sm:grid-cols-3">
          {stats.map((item) => (
            <article
              key={item.label}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <p className="text-sm font-medium text-slate-500">{item.label}</p>
              <p className="mt-2 text-3xl font-bold text-slate-900">{item.value}</p>
              <p className="mt-2 text-xs text-indigo-600">{item.delta}</p>
            </article>
          ))}
        </section>

        <div className="grid gap-6 lg:grid-cols-3">
          <section
            data-ham-section="activity"
            className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-1"
          >
            <h2 className="text-lg font-semibold text-slate-900">Activity</h2>
            <ul className="mt-4 space-y-4">
              {activity.map((item) => (
                <li key={item.text} className="border-l-2 border-indigo-200 pl-3">
                  <p className="text-xs font-medium text-slate-500">{item.time}</p>
                  <p className="mt-1 text-sm text-slate-700">{item.text}</p>
                </li>
              ))}
            </ul>
          </section>

          <section
            data-ham-section="workload"
            className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-2"
          >
            <h2 className="text-lg font-semibold text-slate-900">Team workload</h2>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              {workload.map((member) => (
                <div
                  key={member.name}
                  className="rounded-xl border border-slate-100 bg-slate-50 p-4"
                >
                  <p className="font-semibold text-slate-900">{member.name}</p>
                  <p className="mt-1 text-sm text-slate-600">{member.load}</p>
                  <span className="mt-3 inline-flex rounded-full bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-700">
                    {member.status}
                  </span>
                </div>
              ))}
            </div>
          </section>
        </div>

        <section
          data-ham-section="table"
          className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
        >
          <div className="border-b border-slate-200 px-6 py-4">
            <h2 className="text-lg font-semibold text-slate-900">Projects</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-6 py-3">Project</th>
                  <th className="px-6 py-3">Owner</th>
                  <th className="px-6 py-3">Status</th>
                  <th className="px-6 py-3">Due</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.project} className="border-t border-slate-100">
                    <td className="px-6 py-4 font-medium text-slate-900">{row.project}</td>
                    <td className="px-6 py-4 text-slate-600">{row.owner}</td>
                    <td className="px-6 py-4">
                      <span
                        className={
                          row.status === "At risk"
                            ? "rounded-full bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-800"
                            : "rounded-full bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-800"
                        }
                      >
                        {row.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-slate-600">{row.due}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}
