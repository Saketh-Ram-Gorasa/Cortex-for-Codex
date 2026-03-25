"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  askQuery,
  getDecisionArchaeology,
  getResurrectionPlan,
  listProjects,
  sendSnapshot,
  type TestingDecisionArchaeologyPayload,
  type TestingDecisionArchaeologyResponse,
  type TestingProjectSummary,
  type TestingQueryResponse,
  type TestingResurrectionCommand,
  type TestingResurrectionResponse,
  type TestingSnapshotPayload,
} from "@/components/testing/testingBackendClient";

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

type SessionKind = "anonymous" | "developer" | "developer_guest" | "pm" | "pm_guest";
type PanelMode = "live" | "fallback";

type ChatEntry = {
  role: "assistant" | "user";
  text: string;
  createdAt: string;
  response?: TestingQueryResponse;
  isFallback?: boolean;
  error?: string;
};

type SnapshotStatus = {
  requestId: string;
  requestedAt: string;
  backendStatus: string;
  message: string;
  preview: string;
  mode: PanelMode;
  error?: string;
};

type ArchaeologyFormState = {
  filePath: string;
  symbolName: string;
  signature: string;
  commitHash: string;
  commitMessage: string;
  author: string;
  timestamp: string;
  projectId: string;
};

const DEFAULT_MOCK: SandboxData = {
  mock_id: "TEST_HACKATHON_001",
  description: "Simulation: Backend Engineer debugging JWT auth fallback before a live demo.",
  data: {
    git: { branch: "auth-refactor", status: "dirty" },
    editors: ["src/auth/jwt_handler.ts", "src/auth/session.ts", ".env"],
    secrets_present: ["SECRET_KEY=12345-SUPER-SECRET"],
    last_terminal_command: "pytest tests/test_auth.py -k fallback",
  },
};

const SWARM_STEPS = [
  "Planner frames the synthetic IDE event.",
  "Retriever grounds the query in real backend memory.",
  "Executor returns preview-only guidance.",
  "Fallback protects the judge flow if live calls fail.",
];

const TRUST_PREFIXES = [
  "scope:",
  "confidence:",
  "limitations:",
  "next actions:",
  "next best actions:",
  "sources:",
];

const sessionLabels: Record<SessionKind, string> = {
  anonymous: "No live session",
  developer: "Developer session",
  developer_guest: "Guest developer session",
  pm: "PM session",
  pm_guest: "PM guest session",
};

function redactSecrets(input: string): string {
  return input
    .replace(/AKIA[0-9A-Z]{16}/g, "[REDACTED_AWS_ACCESS_KEY]")
    .replace(/(SECRET_KEY\s*=\s*)([^\n\r]+)/gi, "$1[REDACTED_SECRET]")
    .replace(/(api[_-]?key\s*[:=]\s*)([^\n\r]+)/gi, "$1[REDACTED_API_KEY]")
    .replace(/(Bearer\s+)[A-Za-z0-9._-]+/g, "$1[REDACTED_TOKEN]");
}

function normalizeProjectName(name: string): string {
  return name.toLowerCase().replace(/[\s_-]/g, "");
}

function inferLanguageId(filePath: string): string {
  const ext = filePath.split(".").pop()?.toLowerCase();
  if (ext === "ts" || ext === "tsx") return "typescript";
  if (ext === "js" || ext === "jsx") return "javascript";
  if (ext === "py") return "python";
  if (ext === "json") return "json";
  if (ext === "md") return "markdown";
  return "plaintext";
}

function createRequestId(): string {
  const randomId = globalThis.crypto?.randomUUID?.();
  return randomId ? randomId.slice(0, 12) : `sandbox-${Date.now().toString(36)}`;
}

function formatDateTime(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function toLocalDateTimeInput(date: Date): string {
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function buildCommandLines(commands: TestingResurrectionCommand[]): string[] {
  return commands.flatMap((command) => {
    if (command.type === "git_checkout" && command.branch) return [`Switch branch to \`${command.branch}\``];
    if (command.type === "open_file" && command.filePath) return [`Open file \`${command.filePath}\``];
    if (command.command) return [`Run \`${command.command}\``];
    return [`Preview step: \`${command.type}\``];
  });
}

function buildSourceLines(response: TestingQueryResponse): string[] {
  return (response.sources || []).map((source) => `${source.type || "source"}: ${source.id || source.uri || "unknown"}`);
}

function extractTrustLines(summary: string): string[] {
  return summary
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => TRUST_PREFIXES.some((prefix) => line.toLowerCase().startsWith(prefix)));
}

function buildSyntheticSnapshotPayload(
  mockData: SandboxData,
  dirtyCode: string,
  mission: string,
  projectId?: string,
): TestingSnapshotPayload {
  const primaryFile = mockData.data.editors[0] || "src/demo.ts";
  return {
    timestamp: new Date().toISOString(),
    workspaceFolder: `demo/${mockData.mock_id.toLowerCase()}`,
    activeFile: primaryFile,
    languageId: inferLanguageId(primaryFile),
    shadowGraph: redactSecrets(
      [
        `Scenario: ${mockData.description}`,
        `Mission: ${mission}`,
        `Branch: ${mockData.data.git.branch}`,
        `Editors: ${mockData.data.editors.join(", ")}`,
        `Last command: ${mockData.data.last_terminal_command}`,
        "",
        dirtyCode,
      ].join("\n"),
    ),
    gitBranch: mockData.data.git.branch,
    projectId,
    terminalCommands: [mockData.data.last_terminal_command],
    functionContext: {
      source: "testing_sandbox",
      simulated: true,
      mockId: mockData.mock_id,
      mission,
      gitStatus: mockData.data.git.status,
    },
  };
}

function buildFallbackChatResponse(question: string, projectId?: string): TestingQueryResponse {
  return {
    summary: [
      `Scope: ${projectId ? `Selected project ${projectId}` : "Testing sandbox hybrid demo"}`,
      "Confidence: 68%",
      "Limitations: Backend retrieval failed, so this answer is deterministic fallback output.",
      "Next actions: Reconnect backend, capture a fresh simulated snapshot, and retry the live query.",
      "",
      `Answer: For "${question}", the demo hypothesis is that the auth regression started during the JWT fallback refactor on \`auth-refactor\`.`,
    ].join("\n"),
    reasoningLog: ["Used canned fallback because the live backend call failed."],
    commands: [
      { type: "git_checkout", branch: "auth-refactor" },
      { type: "open_file", filePath: "src/auth/jwt_handler.ts" },
      { type: "run_command", command: "pytest tests/test_auth.py -k fallback" },
    ],
    sources: [{ type: "fallback", id: "testing-sandbox-chat" }],
    retrievedFacts: [],
    retrievedSnapshots: [],
  };
}

function buildFallbackArchaeologyResponse(
  form: ArchaeologyFormState,
): TestingDecisionArchaeologyResponse {
  return {
    found: true,
    summary: `${form.symbolName} appears to have been adjusted to support a JWT guest-session fallback near commit ${form.commitHash || "abc123"}.`,
    branchesTried: ["auth-refactor", "main", "release/demo"],
    terminalCommands: [
      `git show ${form.commitHash || "abc123"} -- ${form.filePath || "src/auth/service.ts"}`,
      `git blame ${form.filePath || "src/auth/service.ts"}`,
      "pytest tests/test_auth.py -k fallback",
    ],
    confidence: 0.74,
  };
}

function buildFallbackResurrectionResponse(target: string): TestingResurrectionResponse {
  return {
    planSummary: `Preview-only recovery plan for ${target || "auth-refactor"} generated from the sandbox fallback script.`,
    commands: [
      { type: "git_checkout", branch: target || "auth-refactor" },
      { type: "open_file", filePath: "src/auth/jwt_handler.ts" },
      { type: "open_file", filePath: "src/auth/session.ts" },
      { type: "run_command", command: "pytest tests/test_auth.py -k fallback" },
    ],
    impactAnalysis: {
      conflicts: ["Workspace contains unstaged auth edits that should be reviewed before restore."],
      unstashedChanges: true,
      estimatedRisk: "medium",
    },
  };
}

function buildLiveQuestion(prompt: string, projectId?: string): string {
  return [
    "Demo mode note: IDE events are simulated in the /testing sandbox.",
    projectId ? `Project scope hint: ${projectId}` : "Project scope hint: not set.",
    "Return grounded guidance and preserve trust language such as scope, confidence, limitations, next actions, and sources when available.",
    "",
    `User question: ${prompt}`,
  ].join("\n");
}

const textareaStyle = {
  width: "100%",
  background: "rgba(8, 8, 8, 0.75)",
  border: "1px solid rgba(255,255,255,0.1)",
  color: "#f0f0f0",
  fontFamily: "var(--font-mono)",
  fontSize: 12,
  padding: 12,
  borderRadius: 12,
} as const;

export default function TestingSandbox() {
  const backendUrl =
    process.env.NEXT_PUBLIC_BACKEND_URL || "https://sc-backend-suhaan.azurewebsites.net";

  const [token, setToken] = useState("");
  const [sessionKind, setSessionKind] = useState<SessionKind>("anonymous");
  const [projects, setProjects] = useState<TestingProjectSummary[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [projectOverride, setProjectOverride] = useState("");
  const [projectLoading, setProjectLoading] = useState(false);
  const [projectError, setProjectError] = useState("");
  const [fallbackEnabled, setFallbackEnabled] = useState(false);

  const [mockData, setMockData] = useState(DEFAULT_MOCK);
  const [mockEditor, setMockEditor] = useState(JSON.stringify(DEFAULT_MOCK, null, 2));
  const [editorError, setEditorError] = useState("");
  const [swarmStep, setSwarmStep] = useState(0);
  const [swarmMission] = useState(
    "Capture a realistic auth regression snapshot and push it through the real backend.",
  );
  const [dirtyCode, setDirtyCode] = useState(
    "const API_KEY = 'AKIAIOSFODNN7EXAMPLE';\nconst SECRET_KEY=12345-SUPER-SECRET;\nAuthorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
  );
  const [redacted, setRedacted] = useState("");

  const [snapshotPending, setSnapshotPending] = useState(false);
  const [snapshotStatus, setSnapshotStatus] = useState<SnapshotStatus | null>(null);

  const [chatPrompt, setChatPrompt] = useState("What changed in auth fallback recently?");
  const [chatPending, setChatPending] = useState(false);
  const [chatLog, setChatLog] = useState<ChatEntry[]>([
    {
      role: "assistant",
      text: "Ask about the simulated workspace. Responses use the real backend when available and disclose fallback output when they do not.",
      createdAt: new Date().toISOString(),
    },
  ]);

  const [archaeologyForm, setArchaeologyForm] = useState<ArchaeologyFormState>({
    filePath: "src/auth/jwt_handler.ts",
    symbolName: "buildGuestFallbackToken",
    signature: "function buildGuestFallbackToken(userId: string): string",
    commitHash: "abc123def456",
    commitMessage: "Tighten guest fallback token handling",
    author: "Hackathon Demo User",
    timestamp: toLocalDateTimeInput(new Date()),
    projectId: "",
  });
  const [archaeologyPending, setArchaeologyPending] = useState(false);
  const [archaeologyResult, setArchaeologyResult] = useState<{
    data: TestingDecisionArchaeologyResponse;
    mode: PanelMode;
    error?: string;
  } | null>(null);

  const [resurrectionTarget, setResurrectionTarget] = useState("auth-refactor");
  const [resurrectionPending, setResurrectionPending] = useState(false);
  const [resurrectionResult, setResurrectionResult] = useState<{
    data: TestingResurrectionResponse;
    mode: PanelMode;
    error?: string;
  } | null>(null);

  const activeProjectId = projectOverride.trim() || selectedProjectId || "";
  const activeProjectName =
    projects.find((project) => project.id === selectedProjectId)?.name ||
    activeProjectId ||
    "Not set";
  const isPmGuest = sessionKind === "pm_guest";

  useEffect(() => {
    if (typeof window === "undefined") return;
    const storedToken = window.localStorage.getItem("sc_jwt_token") || "";
    const nextKind: SessionKind = !storedToken
      ? "anonymous"
      : window.localStorage.getItem("sc_pm_guest_mode") === "true"
        ? "pm_guest"
        : window.localStorage.getItem("sc_pm_mode") === "auth"
          ? "pm"
          : window.localStorage.getItem("sc_dev_guest_mode") === "true"
            ? "developer_guest"
            : "developer";
    setToken(storedToken);
    setSessionKind(nextKind);
  }, []);

  useEffect(() => {
    if (!token || isPmGuest) {
      setProjects([]);
      return;
    }
    let cancelled = false;
    const loadProjects = async () => {
      setProjectLoading(true);
      setProjectError("");
      try {
        const nextProjects = (await listProjects(token, backendUrl)).filter(
          (project) => !project.is_archived,
        );
        if (cancelled) return;
        setProjects(nextProjects);
        setSelectedProjectId((current) => {
          if (current && nextProjects.some((project) => project.id === current)) return current;
          const preferred =
            nextProjects.find((project) =>
              normalizeProjectName(project.name).includes("secondcortex"),
            ) || nextProjects[0];
          return preferred?.id || "";
        });
      } catch (error) {
        if (cancelled) return;
        setProjectError(
          error instanceof Error
            ? error.message
            : "Could not load project scopes for /testing.",
        );
      } finally {
        if (!cancelled) setProjectLoading(false);
      }
    };
    void loadProjects();
    return () => {
      cancelled = true;
    };
  }, [backendUrl, isPmGuest, token]);

  const chipStyle = {
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
    padding: "6px 10px",
    borderRadius: 999,
    border: "1px solid rgba(255,255,255,0.14)",
    fontFamily: "var(--font-mono)",
    fontSize: 11,
  } as const;

  const fallbackBadge = {
    ...chipStyle,
    border: "1px solid rgba(255,184,77,0.45)",
    background: "rgba(255,184,77,0.12)",
    color: "#ffd38a",
  } as const;

  const handleInjectJson = () => {
    try {
      setMockData(JSON.parse(mockEditor) as SandboxData);
      setEditorError("");
    } catch {
      setEditorError("The simulated IDE JSON is invalid. Fix the formatting and try again.");
    }
  };

  const handleSnapshot = async () => {
    const payload = buildSyntheticSnapshotPayload(
      mockData,
      dirtyCode,
      swarmMission,
      activeProjectId || undefined,
    );
    const preview = JSON.stringify(payload, null, 2);
    setSnapshotPending(true);
    try {
      const response = await sendSnapshot(payload, token, backendUrl);
      setSnapshotStatus({
        requestId: createRequestId(),
        requestedAt: new Date().toISOString(),
        backendStatus: response.status,
        message: response.message,
        preview,
        mode: "live",
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Snapshot capture failed.";
      setSnapshotStatus({
        requestId: createRequestId(),
        requestedAt: new Date().toISOString(),
        backendStatus: fallbackEnabled ? "fallback-output" : "error",
        message: fallbackEnabled
          ? "Rendered canned snapshot acceptance because the live backend call failed."
          : message,
        preview,
        mode: fallbackEnabled ? "fallback" : "live",
        error: message,
      });
    } finally {
      setSnapshotPending(false);
    }
  };

  const handleChat = async () => {
    const trimmed = chatPrompt.trim();
    if (!trimmed || chatPending) return;
    setChatLog((current) => [
      ...current,
      { role: "user", text: trimmed, createdAt: new Date().toISOString() },
    ]);
    setChatPrompt("");
    setChatPending(true);
    try {
      const response = await askQuery(
        buildLiveQuestion(trimmed, activeProjectId || undefined),
        token,
        backendUrl,
        activeProjectId || undefined,
      );
      setChatLog((current) => [
        ...current,
        { role: "assistant", text: response.summary, createdAt: new Date().toISOString(), response },
      ]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Chat request failed.";
      if (fallbackEnabled) {
        const response = buildFallbackChatResponse(trimmed, activeProjectId || undefined);
        setChatLog((current) => [
          ...current,
          {
            role: "assistant",
            text: response.summary,
            createdAt: new Date().toISOString(),
            response,
            isFallback: true,
            error: message,
          },
        ]);
      } else {
        setChatLog((current) => [
          ...current,
          {
            role: "assistant",
            text: `Chatbot error: ${message}`,
            createdAt: new Date().toISOString(),
            error: message,
          },
        ]);
      }
    } finally {
      setChatPending(false);
    }
  };

  const handleArchaeology = async () => {
    const payload: TestingDecisionArchaeologyPayload = {
      filePath: archaeologyForm.filePath.trim(),
      symbolName: archaeologyForm.symbolName.trim(),
      signature: archaeologyForm.signature.trim(),
      commitHash: archaeologyForm.commitHash.trim(),
      commitMessage: archaeologyForm.commitMessage.trim(),
      author: archaeologyForm.author.trim(),
      timestamp: new Date(archaeologyForm.timestamp).toISOString(),
      projectId: archaeologyForm.projectId.trim() || activeProjectId || undefined,
    };
    setArchaeologyPending(true);
    try {
      const response = await getDecisionArchaeology(payload, token, backendUrl);
      setArchaeologyResult({ data: response, mode: "live" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Decision archaeology failed.";
      setArchaeologyResult({
        data: fallbackEnabled
          ? buildFallbackArchaeologyResponse(archaeologyForm)
          : { found: false, summary: null, branchesTried: [], terminalCommands: [], confidence: 0 },
        mode: fallbackEnabled ? "fallback" : "live",
        error: message,
      });
    } finally {
      setArchaeologyPending(false);
    }
  };

  const handleResurrection = async () => {
    setResurrectionPending(true);
    try {
      const response = await getResurrectionPlan(resurrectionTarget.trim(), token, backendUrl);
      setResurrectionResult({ data: response, mode: "live" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Resurrection preview failed.";
      setResurrectionResult({
        data: fallbackEnabled
          ? buildFallbackResurrectionResponse(resurrectionTarget.trim())
          : { commands: [], planSummary: null, impactAnalysis: null },
        mode: fallbackEnabled ? "fallback" : "live",
        error: message,
      });
    } finally {
      setResurrectionPending(false);
    }
  };

  return (
    <main className="sc-shell" style={{ minHeight: "100vh", padding: "120px 24px 40px" }}>
      <div style={{ maxWidth: 1240, margin: "0 auto", display: "grid", gap: 16 }}>
        <header className="sc-dashboard-panel">
          <div
            className="sc-dashboard-panel-inner"
            style={{ flexDirection: "column", alignItems: "stretch", gap: 16 }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: 16,
                alignItems: "flex-start",
                flexWrap: "wrap",
              }}
            >
              <div style={{ maxWidth: 760 }}>
                <p className="section-label">Hackathon Demo Sandbox</p>
                <h1 className="section-title" style={{ marginBottom: 8 }}>
                  Real backend responses, simulated IDE event source
                </h1>
                <p className="section-desc" style={{ maxWidth: 760 }}>
                  `/testing` is now a hybrid demo shell: the editor JSON and event source remain
                  synthetic, while snapshot ingestion, chat, decision archaeology, and resurrection
                  preview call the real SecondCortex backend whenever auth allows it.
                </p>
              </div>
              <div style={{ display: "grid", gap: 10, minWidth: 280 }}>
                <button
                  className="btn-primary"
                  onClick={() => {
                    setMockData(DEFAULT_MOCK);
                    setMockEditor(JSON.stringify(DEFAULT_MOCK, null, 2));
                    setEditorError("");
                  }}
                  type="button"
                >
                  Load Demo Data
                </button>
                <button className="btn-secondary" onClick={handleInjectJson} type="button">
                  Apply JSON to Sandbox
                </button>
                <Link
                  href="/testing/readme"
                  className="btn-secondary"
                  style={{ textDecoration: "none", textAlign: "center" }}
                >
                  Open Sandbox README
                </Link>
              </div>
            </div>

            <div className="sc-guide-grid" style={{ gridTemplateColumns: "1.2fr 0.8fr" }}>
              <div
                className="sc-guide-card"
                style={{ display: "grid", gap: 12, borderColor: "rgba(84, 190, 255, 0.32)" }}
              >
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <span style={chipStyle}>Trust Banner</span>
                  <span style={chipStyle}>Real backend responses</span>
                  <span style={chipStyle}>Simulated IDE events</span>
                </div>
                <p className="sc-auth-sub" style={{ margin: 0 }}>
                  Disclosure for judges: this page generates synthetic IDE events. Once captured, the
                  backend processing path is real.
                </p>
                {isPmGuest ? (
                  <p className="sc-modal-warn" style={{ marginTop: 0 }}>
                    PM guest tokens can use chat, but snapshot ingestion and protected preview
                    endpoints may intentionally return `403`.
                  </p>
                ) : null}
              </div>

              <div className="sc-guide-card" style={{ display: "grid", gap: 10 }}>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <span style={chipStyle}>Session: {sessionLabels[sessionKind]}</span>
                  <span style={chipStyle}>Project: {activeProjectName}</span>
                </div>
                <select
                  value={selectedProjectId}
                  onChange={(event) => setSelectedProjectId(event.target.value)}
                  disabled={!token || isPmGuest || projectLoading}
                  className="sc-auth-input"
                >
                  <option value="">No project selected</option>
                  {projects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                    </option>
                  ))}
                </select>
                <input
                  className="sc-auth-input"
                  value={projectOverride}
                  onChange={(event) => setProjectOverride(event.target.value)}
                  placeholder="Optional projectId override"
                />
                <label
                  className="sc-auth-sub"
                  style={{ display: "inline-flex", alignItems: "center", gap: 10 }}
                >
                  <input
                    type="checkbox"
                    checked={fallbackEnabled}
                    onChange={(event) => setFallbackEnabled(event.target.checked)}
                  />
                  Use canned demo fallback when backend fails
                </label>
                {!token ? (
                  <p className="sc-modal-warn" style={{ marginTop: 0 }}>
                    Log in first to exercise the live backend path. The simulation shell still works
                    without auth.
                  </p>
                ) : null}
                {projectError ? <p className="sc-auth-error">{projectError}</p> : null}
              </div>
            </div>
          </div>
        </header>

        <section className="sc-guide-grid" style={{ gridTemplateColumns: "1.2fr 0.8fr" }}>
          <div className="sc-guide-card" style={{ display: "grid", gap: 10 }}>
            <h2 className="sc-guide-title">1. Simulated IDE Event Source</h2>
            <textarea
              value={mockEditor}
              onChange={(event) => setMockEditor(event.target.value)}
              style={{ ...textareaStyle, minHeight: 300 }}
            />
            {editorError ? <p className="sc-auth-error">{editorError}</p> : null}
          </div>

          <div className="sc-guide-card" style={{ display: "grid", gap: 10 }}>
            <h2 className="sc-guide-title">Simulation Summary</h2>
            <p className="sc-auth-sub">
              <strong>ID:</strong> {mockData.mock_id}
            </p>
            <p className="sc-auth-sub">
              <strong>Description:</strong> {mockData.description}
            </p>
            <p className="sc-auth-sub">
              <strong>Branch:</strong> {mockData.data.git.branch}
            </p>
            <p className="sc-auth-sub">
              <strong>Editors:</strong> {mockData.data.editors.join(", ")}
            </p>
            <p className="sc-auth-sub">
              <strong>Mission:</strong> {swarmMission}
            </p>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button
                className="btn-secondary"
                type="button"
                onClick={() => setSwarmStep((current) => Math.max(0, current - 1))}
              >
                Previous Step
              </button>
              <button
                className="btn-primary"
                type="button"
                onClick={() =>
                  setSwarmStep((current) => Math.min(SWARM_STEPS.length - 1, current + 1))
                }
              >
                Next Step
              </button>
            </div>
            <p className="sc-auth-sub" style={{ marginBottom: 0 }}>
              <strong>Step {swarmStep + 1}:</strong> {SWARM_STEPS[swarmStep]}
            </p>
          </div>
        </section>

        <section className="sc-guide-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <div className="sc-guide-card" style={{ display: "grid", gap: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <div>
                <h2 className="sc-dashboard-h2">2. Snapshot Capture</h2>
                <p className="sc-dashboard-p" style={{ marginBottom: 0 }}>
                  The button below sends a real `/api/v1/snapshot` request using the synthetic IDE
                  state from this page.
                </p>
              </div>
              <button className="btn-primary" type="button" onClick={handleSnapshot} disabled={snapshotPending}>
                {snapshotPending ? "Capturing..." : "Capture Snapshot (Simulated IDE Event)"}
              </button>
            </div>

            {snapshotStatus ? (
              <div className="sc-guide-card" style={{ display: "grid", gap: 10, padding: 16 }}>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <span style={chipStyle}>Request: {snapshotStatus.requestId}</span>
                  <span style={chipStyle}>Time: {formatDateTime(snapshotStatus.requestedAt)}</span>
                  <span style={chipStyle}>Status: {snapshotStatus.backendStatus}</span>
                  {snapshotStatus.mode === "fallback" ? <span style={fallbackBadge}>Fallback Output</span> : null}
                </div>
                <p className="sc-auth-sub" style={{ marginBottom: 0 }}>
                  {snapshotStatus.message}
                </p>
                {snapshotStatus.error ? (
                  <p className="sc-auth-sub" style={{ marginBottom: 0 }}>
                    Backend detail: {snapshotStatus.error}
                  </p>
                ) : null}
                <pre className="sc-guide-code" style={{ minHeight: 240, whiteSpace: "pre-wrap" }}>
                  {snapshotStatus.preview}
                </pre>
              </div>
            ) : (
              <pre className="sc-guide-code" style={{ minHeight: 240, whiteSpace: "pre-wrap" }}>
                Capture a snapshot to see the request id, timestamp, backend status, and sanitized
                payload preview.
              </pre>
            )}
          </div>

          <div className="sc-guide-card" style={{ display: "grid", gap: 12 }}>
            <div>
              <h2 className="sc-dashboard-h2">3. Sandbox Chat</h2>
              <p className="sc-dashboard-p" style={{ marginBottom: 0 }}>
                Real backend chat with a sandbox preamble. Trust fields are surfaced when present.
              </p>
            </div>
            <div
              style={{
                display: "grid",
                gap: 10,
                maxHeight: 420,
                overflowY: "auto",
                paddingRight: 4,
              }}
            >
              {chatLog.map((entry, index) => (
                <div
                  key={`${entry.role}-${entry.createdAt}-${index}`}
                  className="sc-guide-card"
                  style={{ display: "grid", gap: 10, padding: 14 }}
                >
                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                    <span style={chipStyle}>{entry.role === "user" ? "Judge Prompt" : "Assistant"}</span>
                    <span style={chipStyle}>{formatDateTime(entry.createdAt)}</span>
                    {entry.isFallback ? <span style={fallbackBadge}>Fallback Output</span> : null}
                  </div>
                  <pre className="sc-guide-code" style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                    {entry.text}
                  </pre>
                  {entry.response ? (
                    <>
                      {extractTrustLines(entry.response.summary).length > 0 ? (
                        <div className="sc-auth-sub">
                          Trust: {extractTrustLines(entry.response.summary).join(" | ")}
                        </div>
                      ) : null}
                      {buildCommandLines(entry.response.commands).length > 0 ? (
                        <div className="sc-auth-sub">
                          Actions: {buildCommandLines(entry.response.commands).join(" | ")}
                        </div>
                      ) : null}
                      {buildSourceLines(entry.response).length > 0 ? (
                        <div className="sc-auth-sub">
                          Sources: {buildSourceLines(entry.response).join(" | ")}
                        </div>
                      ) : null}
                    </>
                  ) : null}
                  {entry.error ? (
                    <p className="sc-auth-sub" style={{ marginBottom: 0 }}>
                      Backend detail: {entry.error}
                    </p>
                  ) : null}
                </div>
              ))}
              {chatPending ? <div className="sc-auth-sub">Sending live sandbox query...</div> : null}
            </div>
            <textarea
              value={chatPrompt}
              onChange={(event) => setChatPrompt(event.target.value)}
              style={{ ...textareaStyle, minHeight: 110 }}
            />
            <button className="btn-primary" type="button" onClick={handleChat} disabled={chatPending}>
              {chatPending ? "Querying Backend..." : "Send Sandbox Chat Prompt"}
            </button>
          </div>
        </section>

        <section className="sc-guide-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <div className="sc-guide-card" style={{ display: "grid", gap: 10 }}>
            <div>
              <h2 className="sc-dashboard-h2">4. Decision Archaeology Preview</h2>
              <p className="sc-dashboard-p" style={{ marginBottom: 0 }}>
                Preview on supplied metadata using the real `/api/v1/decision-archaeology` endpoint.
              </p>
            </div>
            <input
              className="sc-auth-input"
              value={archaeologyForm.filePath}
              onChange={(event) =>
                setArchaeologyForm((current) => ({ ...current, filePath: event.target.value }))
              }
              placeholder="File path"
            />
            <input
              className="sc-auth-input"
              value={archaeologyForm.symbolName}
              onChange={(event) =>
                setArchaeologyForm((current) => ({ ...current, symbolName: event.target.value }))
              }
              placeholder="Symbol name"
            />
            <input
              className="sc-auth-input"
              value={archaeologyForm.signature}
              onChange={(event) =>
                setArchaeologyForm((current) => ({ ...current, signature: event.target.value }))
              }
              placeholder="Signature"
            />
            <input
              className="sc-auth-input"
              value={archaeologyForm.commitHash}
              onChange={(event) =>
                setArchaeologyForm((current) => ({ ...current, commitHash: event.target.value }))
              }
              placeholder="Commit hash"
            />
            <input
              className="sc-auth-input"
              value={archaeologyForm.commitMessage}
              onChange={(event) =>
                setArchaeologyForm((current) => ({ ...current, commitMessage: event.target.value }))
              }
              placeholder="Commit message"
            />
            <input
              className="sc-auth-input"
              value={archaeologyForm.author}
              onChange={(event) =>
                setArchaeologyForm((current) => ({ ...current, author: event.target.value }))
              }
              placeholder="Author"
            />
            <input
              className="sc-auth-input"
              type="datetime-local"
              value={archaeologyForm.timestamp}
              onChange={(event) =>
                setArchaeologyForm((current) => ({ ...current, timestamp: event.target.value }))
              }
            />
            <input
              className="sc-auth-input"
              value={archaeologyForm.projectId}
              onChange={(event) =>
                setArchaeologyForm((current) => ({ ...current, projectId: event.target.value }))
              }
              placeholder={activeProjectId || "Optional projectId"}
            />
            <button className="btn-primary" type="button" onClick={handleArchaeology} disabled={archaeologyPending}>
              {archaeologyPending ? "Generating..." : "Run Decision Archaeology Preview"}
            </button>
            {archaeologyResult ? (
              <div className="sc-guide-card" style={{ display: "grid", gap: 10, padding: 16 }}>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <span style={chipStyle}>
                    Confidence: {Math.round((archaeologyResult.data.confidence || 0) * 100)}%
                  </span>
                  {archaeologyResult.mode === "fallback" ? (
                    <span style={fallbackBadge}>Fallback Output</span>
                  ) : null}
                </div>
                <p className="sc-auth-sub" style={{ marginBottom: 0 }}>
                  {archaeologyResult.data.summary ||
                    archaeologyResult.error ||
                    "No archaeology summary was returned."}
                </p>
                {archaeologyResult.data.branchesTried.length > 0 ? (
                  <div className="sc-auth-sub">
                    Branches: {archaeologyResult.data.branchesTried.join(" | ")}
                  </div>
                ) : null}
                {archaeologyResult.data.terminalCommands.length > 0 ? (
                  <div className="sc-auth-sub">
                    Commands: {archaeologyResult.data.terminalCommands.join(" | ")}
                  </div>
                ) : null}
                {archaeologyResult.error ? (
                  <p className="sc-auth-sub" style={{ marginBottom: 0 }}>
                    Backend detail: {archaeologyResult.error}
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="sc-guide-card" style={{ display: "grid", gap: 10 }}>
            <div>
              <h2 className="sc-dashboard-h2">5. Resurrection Preview Only</h2>
              <p className="sc-dashboard-p" style={{ marginBottom: 0 }}>
                This calls the real `/api/v1/resurrect` planner but never executes commands.
              </p>
            </div>
            <input
              className="sc-auth-input"
              value={resurrectionTarget}
              onChange={(event) => setResurrectionTarget(event.target.value)}
              placeholder="feature/auth-fix or snapshot-abc123"
            />
            <button className="btn-primary" type="button" onClick={handleResurrection} disabled={resurrectionPending}>
              {resurrectionPending ? "Generating..." : "Generate Resurrection Preview"}
            </button>
            {resurrectionResult ? (
              <div className="sc-guide-card" style={{ display: "grid", gap: 10, padding: 16 }}>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <span style={chipStyle}>Preview only</span>
                  {resurrectionResult.mode === "fallback" ? (
                    <span style={fallbackBadge}>Fallback Output</span>
                  ) : null}
                </div>
                <p className="sc-auth-sub" style={{ marginBottom: 0 }}>
                  {resurrectionResult.data.planSummary ||
                    resurrectionResult.error ||
                    "No resurrection summary was returned."}
                </p>
                {resurrectionResult.data.impactAnalysis ? (
                  <div className="sc-auth-sub">
                    Impact: risk={resurrectionResult.data.impactAnalysis.estimatedRisk} | unstashed=
                    {resurrectionResult.data.impactAnalysis.unstashedChanges ? "yes" : "no"} | {(resurrectionResult.data.impactAnalysis.conflicts || []).join(" | ")}
                  </div>
                ) : null}
                {resurrectionResult.data.commands.length > 0 ? (
                  <div className="sc-auth-sub">
                    Commands: {buildCommandLines(resurrectionResult.data.commands).join(" | ")}
                  </div>
                ) : null}
                {resurrectionResult.error ? (
                  <p className="sc-auth-sub" style={{ marginBottom: 0 }}>
                    Backend detail: {resurrectionResult.error}
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>
        </section>

        <section className="sc-guide-card" style={{ display: "grid", gap: 10 }}>
          <h2 className="sc-dashboard-h2">6. Semantic Firewall Sanity Check</h2>
          <textarea
            value={dirtyCode}
            onChange={(event) => setDirtyCode(event.target.value)}
            style={{ ...textareaStyle, minHeight: 180 }}
          />
          <button className="btn-primary" type="button" onClick={() => setRedacted(redactSecrets(dirtyCode))}>
            Redact Before Upload
          </button>
          <pre className="sc-guide-code" style={{ minHeight: 180, whiteSpace: "pre-wrap" }}>
            {redacted || "Run the firewall redactor to inspect the sanitized snapshot fragment."}
          </pre>
        </section>
      </div>
    </main>
  );
}
