"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import IncidentDebugGraph, { type IncidentPacket } from "@/components/testing/IncidentDebugGraph";

type SandboxData = {
  mock_id: string;
  description: string;
  data: {
    git: { branch: string; status: "clean" | "dirty" };
    editors: string[];
    secrets_present: string[];
    last_terminal_command: string;
  };
};

const DEFAULT_MOCK: SandboxData = {
  mock_id: "TEST_HACKATHON_001",
  description: "Simulation: Backend Engineer working on JWT Auth",
  data: {
    git: { branch: "auth-refactor", status: "dirty" },
    editors: ["auth.py", "jwt_handler.py", ".env"],
    secrets_present: ["SECRET_KEY=12345-SUPER-SECRET"],
    last_terminal_command: "pytest tests/test_auth.py",
  },
};

const SWARM_STEPS = [
  "Planner receives request and drafts the resurrection plan.",
  "Retriever pulls semantic memory matches for the target context.",
  "Executor compiles workspace commands and safety checks.",
  "Simulator confirms no destructive conflict before execution.",
];

function redactSecrets(input: string): string {
  return input
    .replace(/AKIA[0-9A-Z]{16}/g, "[REDACTED_AWS_ACCESS_KEY]")
    .replace(/(SECRET_KEY\s*=\s*)([^\n\r]+)/gi, "$1[REDACTED_SECRET]")
    .replace(/(api[_-]?key\s*[:=]\s*)([^\n\r]+)/gi, "$1[REDACTED_API_KEY]")
    .replace(/(Bearer\s+)[A-Za-z0-9._-]+/g, "$1[REDACTED_TOKEN]");
}

function generateDryRunCommands(snapshot: SandboxData): string[] {
  const commands: string[] = [];
  if (snapshot.data.git.status === "dirty") {
    commands.push('git stash push -u -m "secondcortex-auto-stash"');
  }
  commands.push(`git checkout ${snapshot.data.git.branch}`);
  snapshot.data.editors.forEach((file) => commands.push(`code ${file}`));
  commands.push(snapshot.data.last_terminal_command);
  commands.push("echo 'Simulator: dry-run completed. No command executed.'");
  return commands;
}

export default function TestingSandbox() {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "https://sc-backend-suhaan.azurewebsites.net";
  const [mockData, setMockData] = useState<SandboxData>(DEFAULT_MOCK);
  const [mockEditor, setMockEditor] = useState(JSON.stringify(DEFAULT_MOCK, null, 2));
  const [swarmStep, setSwarmStep] = useState(0);
  const [swarmMission, setSwarmMission] = useState("Inject a 'Stripe Debugging' context.");
  const [dirtyCode, setDirtyCode] = useState(
    "const API_KEY = 'AKIAIOSFODNN7EXAMPLE';\nconst SECRET_KEY=12345-SUPER-SECRET;\nAuthorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" 
  );
  const [redacted, setRedacted] = useState("");
  const [dryRunCommands, setDryRunCommands] = useState<string[]>([]);
  const [incidentQuestion, setIncidentQuestion] = useState("Why auth failed after deploy?");
  const [incidentTimeWindow, setIncidentTimeWindow] = useState("24h");
  const [incidentLoading, setIncidentLoading] = useState(false);
  const [incidentError, setIncidentError] = useState("");
  const [incidentPacket, setIncidentPacket] = useState<IncidentPacket | null>(null);

  const plannerOutput = useMemo(() => {
    return [
      "Restore branch context",
      "Open auth files",
      "Run previous failing test",
      mockData.data.git.status === "dirty" ? "Insert safety stash command" : "Skip stash, workspace clean",
    ];
  }, [mockData]);

  const retrieverOutput = useMemo(() => {
    return [
      `Top memory match: ${mockData.description}`,
      `Editors recalled: ${mockData.data.editors.join(", ")}`,
      `Last command recalled: ${mockData.data.last_terminal_command}`,
    ];
  }, [mockData]);

  const loadMockData = () => {
    setMockData(DEFAULT_MOCK);
    setMockEditor(JSON.stringify(DEFAULT_MOCK, null, 2));
    setSwarmMission("Inject a 'Stripe Debugging' context.");
  };

  const injectFromEditor = () => {
    try {
      const parsed = JSON.parse(mockEditor) as SandboxData;
      setMockData(parsed);
    } catch {
      alert("Invalid JSON in mock editor. Please fix formatting.");
    }
  };

  const runSwarmMission = () => {
    setSwarmMission(
      "Inject a 'Stripe Debugging' context. Watch the Planner calculate the Git commands while the Retriever pulls the vector match."
    );
    setSwarmStep(0);
  };

  const runRedactor = () => {
    setRedacted(redactSecrets(dirtyCode));
  };

  const runEmergencyHotfix = () => {
    setDryRunCommands(generateDryRunCommands(mockData));
  };

  const loadIncidentPacket = async () => {
    setIncidentLoading(true);
    setIncidentError("");

    try {
      const token = localStorage.getItem("sc_jwt_token") || "";
      if (!token) {
        setIncidentError("Please log in first so /testing can call the protected incident endpoint.");
        setIncidentLoading(false);
        return;
      }

      const response = await fetch(`${backendUrl}/api/v1/incident/packet`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ question: incidentQuestion, timeWindow: incidentTimeWindow }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || `Request failed with status ${response.status}`);
      }

      const payload = (await response.json()) as IncidentPacket;
      setIncidentPacket(payload);
    } catch (error) {
      setIncidentPacket(null);
      setIncidentError(error instanceof Error ? error.message : "Failed to load incident packet.");
    } finally {
      setIncidentLoading(false);
    }
  };

  return (
    <main className="sc-shell" style={{ minHeight: "100vh", padding: "120px 24px 40px" }}>
      <div style={{ maxWidth: 1200, margin: "0 auto", display: "grid", gap: 16 }}>
        <header className="sc-dashboard-panel">
          <div className="sc-dashboard-panel-inner" style={{ alignItems: "flex-start" }}>
            <div>
              <p className="section-label">SecondCortex Testing Sandbox</p>
              <h1 className="section-title" style={{ marginBottom: 8 }}>Testable Features and Mission Control</h1>
              <p className="section-desc" style={{ maxWidth: 760 }}>
                Safe mock-only environment for judges. This route performs no production writes and does not require login.
              </p>
            </div>
            <div style={{ display: "grid", gap: 10, minWidth: 280 }}>
              <button className="btn-primary" onClick={loadMockData} type="button">Load Mock Data</button>
              <button className="btn-secondary" onClick={injectFromEditor} type="button">Inject JSON</button>
            </div>
          </div>
        </header>

        <section className="sc-guide-grid" style={{ gridTemplateColumns: "1.3fr 1fr" }}>
          <div className="sc-guide-card">
            <h2 className="sc-guide-title">Judge Sandbox: Mock Snapshot Data</h2>
            <textarea
              value={mockEditor}
              onChange={(e) => setMockEditor(e.target.value)}
              style={{
                width: "100%",
                minHeight: 280,
                background: "rgba(8,8,8,0.75)",
                border: "1px solid rgba(255,255,255,0.1)",
                color: "#f0f0f0",
                fontFamily: "var(--font-mono)",
                fontSize: 12,
                padding: 12,
              }}
            />
          </div>
          <div className="sc-guide-card" style={{ display: "grid", gap: 10 }}>
            <h2 className="sc-guide-title">Live Mock Summary</h2>
            <p className="sc-auth-sub"><strong>ID:</strong> {mockData.mock_id}</p>
            <p className="sc-auth-sub"><strong>Description:</strong> {mockData.description}</p>
            <p className="sc-auth-sub"><strong>Branch:</strong> {mockData.data.git.branch}</p>
            <p className="sc-auth-sub"><strong>Status:</strong> {mockData.data.git.status}</p>
            <p className="sc-auth-sub"><strong>Editors:</strong> {mockData.data.editors.join(", ")}</p>
          </div>
        </section>

        <section className="sc-dashboard-panel">
          <div className="sc-dashboard-panel-inner" style={{ flexDirection: "column", alignItems: "stretch" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <h2 className="sc-dashboard-h2">1. Agent Swarm Simulation</h2>
              <button className="btn-secondary" onClick={runSwarmMission} type="button">Run Mission</button>
            </div>
            <p className="sc-dashboard-p">Mission: {swarmMission}</p>

            <div className="sc-stats-grid">
              {[
                { label: "Planner", text: plannerOutput.join(" | ") },
                { label: "Retriever", text: retrieverOutput.join(" | ") },
                { label: "Executor", text: "Preparing deterministic command array for dry-run only." },
              ].map((item, idx) => (
                <div key={item.label} className="sc-stat-card" style={{ borderColor: swarmStep === idx ? "rgba(255,255,255,0.4)" : undefined }}>
                  <div className="sc-stat-title">{item.label}</div>
                  <p className="sc-auth-sub" style={{ marginTop: 10 }}>{item.text}</p>
                </div>
              ))}
            </div>

            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button className="btn-secondary" type="button" onClick={() => setSwarmStep((s) => Math.max(0, s - 1))}>Previous Step</button>
              <button className="btn-primary" type="button" onClick={() => setSwarmStep((s) => Math.min(SWARM_STEPS.length - 1, s + 1))}>Next Step</button>
              <div className="sc-auth-sub" style={{ alignSelf: "center" }}>Step {swarmStep + 1}: {SWARM_STEPS[swarmStep]}</div>
            </div>
          </div>
        </section>

        <section className="sc-guide-grid">
          <div className="sc-guide-card" style={{ display: "grid", gap: 10 }}>
            <h2 className="sc-dashboard-h2">2. Semantic Firewall Redactor</h2>
            <p className="sc-dashboard-p">Mission: Paste a real-looking AWS Secret Key and verify redaction before cloud logs.</p>
            <textarea
              value={dirtyCode}
              onChange={(e) => setDirtyCode(e.target.value)}
              style={{
                width: "100%",
                minHeight: 200,
                background: "rgba(8,8,8,0.75)",
                border: "1px solid rgba(255,255,255,0.1)",
                color: "#f0f0f0",
                fontFamily: "var(--font-mono)",
                fontSize: 12,
                padding: 12,
              }}
            />
            <button className="btn-primary" type="button" onClick={runRedactor}>Redact Before Upload</button>
          </div>

          <div className="sc-guide-card" style={{ display: "grid", gap: 10 }}>
            <h3 className="sc-guide-title">Sanitized Output</h3>
            <pre className="sc-guide-code" style={{ minHeight: 240, whiteSpace: "pre-wrap" }}>
              {redacted || "Run the firewall redactor to see sanitized output."}
            </pre>
          </div>
        </section>

        <section className="sc-dashboard-panel">
          <div className="sc-dashboard-panel-inner" style={{ flexDirection: "column", alignItems: "stretch" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <h2 className="sc-dashboard-h2">3. Workspace Resurrection Dry-Run</h2>
              <button className="btn-primary" onClick={runEmergencyHotfix} type="button">Run Emergency Hotfix Mission</button>
            </div>
            <p className="sc-dashboard-p">
              Mission: Observe command generation. If local env is dirty, Executor auto-inserts stash before branch/file restoration.
            </p>
            <pre className="sc-guide-code" style={{ minHeight: 210, whiteSpace: "pre-wrap" }}>
              {dryRunCommands.length > 0
                ? JSON.stringify(dryRunCommands, null, 2)
                : "Run mission to generate the executor command array."}
            </pre>
          </div>
        </section>

        <section className="sc-guide-card" style={{ textAlign: "center", display: "grid", gap: 10 }}>
          <div style={{ display: "grid", gap: 10, textAlign: "left" }}>
            <h2 className="sc-dashboard-h2">4. Incident Packet Query</h2>
            <p className="sc-dashboard-p">Fetch a real incident packet and render evidence, hypotheses, and recovery simulation.</p>
            <textarea
              value={incidentQuestion}
              onChange={(e) => setIncidentQuestion(e.target.value)}
              style={{ width: "100%", minHeight: 90 }}
            />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <label className="sc-auth-sub" style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                Time Window
                <select value={incidentTimeWindow} onChange={(e) => setIncidentTimeWindow(e.target.value)}>
                  <option value="6h">6h</option>
                  <option value="24h">24h</option>
                  <option value="72h">72h</option>
                </select>
              </label>
              <button className="btn-primary" type="button" onClick={loadIncidentPacket} disabled={incidentLoading}>
                {incidentLoading ? "Loading Incident Packet..." : "Load Incident Packet"}
              </button>
            </div>
            {incidentError ? <p className="sc-auth-sub">{incidentError}</p> : null}
          </div>
          {incidentPacket ? <IncidentDebugGraph packet={incidentPacket} /> : null}

          <Link href="/testing/readme" className="btn-primary" style={{ textDecoration: "none", display: "inline-block" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M3 2.5h7l3 3v8H3z" />
                <path d="M10 2.5v3h3" />
                <path d="M5.5 9h5" />
              </svg>
              Full Text in your VSCode
            </span>
          </Link>
          <p className="sc-auth-sub">
            Ready to stop simulating? View the full README to install the SecondCortex VSIX and start resurrecting your actual workspace.
          </p>
        </section>
      </div>
    </main>
  );
}
