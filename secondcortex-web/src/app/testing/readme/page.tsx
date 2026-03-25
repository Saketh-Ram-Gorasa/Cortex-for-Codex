export const metadata = {
  title: "SecondCortex Testing README",
  description:
    "Judge-facing guide for the hybrid /testing sandbox with real backend calls and simulated IDE events.",
};

export default function TestingReadmePage() {
  return (
    <main className="sc-shell" style={{ minHeight: "100vh", padding: "120px 24px 40px" }}>
      <div
        className="sc-guide-card"
        style={{ maxWidth: 980, margin: "0 auto", display: "grid", gap: 16 }}
      >
        <p className="section-label">Testing Sandbox README</p>
        <h1 className="section-title" style={{ marginBottom: 0 }}>
          Hybrid Demo Sandbox Runbook
        </h1>
        <p className="section-desc" style={{ maxWidth: 760 }}>
          `/testing` is no longer mock-only. It is a hybrid demo shell: IDE events are simulated in
          the page, while backend processing uses the real authenticated SecondCortex APIs when
          available.
        </p>

        <section style={{ display: "grid", gap: 8 }}>
          <h2 className="sc-guide-title">1. What Is Simulated</h2>
          <p className="sc-auth-sub">
            The JSON editor, swarm narration, and synthetic editor payload are generated inside the
            web app so judges can inspect the input state before anything is sent.
          </p>
        </section>

        <section style={{ display: "grid", gap: 8 }}>
          <h2 className="sc-guide-title">2. What Is Real</h2>
          <p className="sc-auth-sub">
            Snapshot capture calls `/api/v1/snapshot`, sandbox chat calls the live query endpoint,
            archaeology uses `/api/v1/decision-archaeology`, and resurrection preview calls
            `/api/v1/resurrect`.
          </p>
        </section>

        <section style={{ display: "grid", gap: 8 }}>
          <h2 className="sc-guide-title">3. Recommended Judge Flow</h2>
          <p className="sc-auth-sub">
            Load demo data, disclose that IDE events are simulated, capture a snapshot, ask a
            sandbox question, run archaeology on a supplied symbol, and finish with a preview-only
            resurrection plan.
          </p>
        </section>

        <section style={{ display: "grid", gap: 8 }}>
          <h2 className="sc-guide-title">4. Safety Fallback</h2>
          <p className="sc-auth-sub">
            Turn on `Use canned demo fallback when backend fails` before a live demo if you want
            deterministic output during transient outages. Fallback output is always explicitly
            labeled.
          </p>
        </section>

        <section style={{ display: "grid", gap: 8 }}>
          <h2 className="sc-guide-title">5. When To Switch To VSIX</h2>
          <p className="sc-auth-sub">
            Use the VSIX when you want actual editor telemetry, natural snapshot capture, and full
            workspace resurrection execution. `/testing` is intentionally a transparent simulation
            shell.
          </p>
        </section>

        <p className="sc-modal-warn" style={{ marginTop: 6 }}>
          Suggested disclosure: &quot;This sandbox uses real backend responses, but the IDE event
          source is simulated in the browser for demo clarity.&quot;
        </p>
      </div>
    </main>
  );
}
