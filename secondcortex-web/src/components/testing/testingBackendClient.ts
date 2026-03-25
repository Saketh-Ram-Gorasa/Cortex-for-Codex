"use client";

export class TestingBackendError extends Error {
  status: number | null;
  detail: string;

  constructor(message: string, status: number | null, detail = "") {
    super(message);
    this.name = "TestingBackendError";
    this.status = status;
    this.detail = detail;
  }
}

export interface TestingProjectSummary {
  id: string;
  name: string;
  visibility: "private" | "team";
  is_archived: boolean;
}

export interface TestingSnapshotPayload {
  timestamp: string;
  workspaceFolder: string;
  activeFile: string;
  languageId: string;
  shadowGraph: string;
  gitBranch?: string | null;
  projectId?: string;
  terminalCommands: string[];
  functionContext?: Record<string, unknown>;
}

export interface TestingSnapshotResponse {
  status: string;
  message: string;
}

export interface TestingQuerySource {
  type?: string;
  id?: string;
  uri?: string;
}

export interface TestingResurrectionCommand {
  type: string;
  branch?: string | null;
  filePath?: string | null;
  viewColumn?: number | null;
  command?: string | null;
}

export interface TestingQueryResponse {
  summary: string;
  reasoningLog: string[];
  commands: TestingResurrectionCommand[];
  sources: TestingQuerySource[];
  retrievedFacts: Record<string, unknown>[];
  retrievedSnapshots: Record<string, unknown>[];
}

export interface TestingResurrectionImpactAnalysis {
  conflicts: string[];
  unstashedChanges: boolean;
  estimatedRisk: string;
}

export interface TestingResurrectionResponse {
  commands: TestingResurrectionCommand[];
  planSummary: string | null;
  impactAnalysis: TestingResurrectionImpactAnalysis | null;
}

export interface TestingDecisionArchaeologyPayload {
  filePath: string;
  symbolName: string;
  signature: string;
  commitHash: string;
  commitMessage: string;
  author: string;
  timestamp: string;
  projectId?: string;
}

export interface TestingDecisionArchaeologyResponse {
  found: boolean;
  summary: string | null;
  branchesTried: string[];
  terminalCommands: string[];
  confidence: number;
}

type UnknownRecord = Record<string, unknown>;

function normalizeBackendUrl(backendUrl: string): string {
  return backendUrl.replace(/\/+$/, "");
}

function ensureToken(token: string): void {
  if (!token.trim()) {
    throw new TestingBackendError("Log in to use the live sandbox backend panels.", 401);
  }
}

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNullableString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asBoolean(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter((item): item is string => typeof item === "string");
}

function asObjectArray(value: unknown): UnknownRecord[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter(isRecord);
}

async function readResponseBody(response: Response): Promise<unknown> {
  const text = await response.text().catch(() => "");
  if (!text.trim()) {
    return null;
  }

  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

function extractErrorMessage(body: unknown, status: number): string {
  if (typeof body === "string" && body.trim()) {
    return body.trim();
  }

  if (isRecord(body)) {
    const detail = body.detail;
    const message = body.message;
    const error = body.error;
    if (typeof detail === "string" && detail.trim()) {
      return detail.trim();
    }
    if (typeof message === "string" && message.trim()) {
      return message.trim();
    }
    if (typeof error === "string" && error.trim()) {
      return error.trim();
    }
  }

  return `Request failed with status ${status}.`;
}

async function requestJson<T>(
  path: string,
  token: string,
  backendUrl: string,
  init: RequestInit,
): Promise<T> {
  ensureToken(token);

  let response: Response;
  try {
    response = await fetch(`${normalizeBackendUrl(backendUrl)}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...(init.headers || {}),
      },
    });
  } catch (error) {
    throw new TestingBackendError(
      error instanceof Error ? error.message : "Network error reaching the backend.",
      null,
    );
  }

  const body = await readResponseBody(response);
  if (!response.ok) {
    throw new TestingBackendError(
      extractErrorMessage(body, response.status),
      response.status,
      typeof body === "string" ? body : JSON.stringify(body ?? {}),
    );
  }

  if (!isRecord(body) && !Array.isArray(body)) {
    throw new TestingBackendError("Backend returned an unexpected response shape.", response.status);
  }

  return body as T;
}

function shouldUsePmQueryEndpoint(): boolean {
  if (typeof window === "undefined") {
    return false;
  }

  return (
    window.localStorage.getItem("sc_pm_mode") === "auth" ||
    window.localStorage.getItem("sc_pm_guest_mode") === "true"
  );
}

function normalizeCommand(raw: UnknownRecord): TestingResurrectionCommand {
  return {
    type: asString(raw.type, "step"),
    branch: asNullableString(raw.branch),
    filePath: asNullableString(raw.filePath ?? raw.file_path),
    viewColumn: typeof raw.viewColumn === "number" ? raw.viewColumn : null,
    command: asNullableString(raw.command),
  };
}

function normalizeQueryResponse(raw: unknown): TestingQueryResponse {
  const record = isRecord(raw) ? raw : {};
  return {
    summary: asString(record.summary, "No answer was returned."),
    reasoningLog: asStringArray(record.reasoningLog ?? record.reasoning_log),
    commands: asObjectArray(record.commands).map(normalizeCommand),
    sources: asObjectArray(record.sources).map((source) => ({
      type: asNullableString(source.type) ?? undefined,
      id: asNullableString(source.id) ?? undefined,
      uri: asNullableString(source.uri) ?? undefined,
    })),
    retrievedFacts: asObjectArray(record.retrievedFacts ?? record.retrieved_facts),
    retrievedSnapshots: asObjectArray(record.retrievedSnapshots ?? record.retrieved_snapshots),
  };
}

function normalizeResurrectionResponse(raw: unknown): TestingResurrectionResponse {
  const record = isRecord(raw) ? raw : {};
  const impactRaw = record.impactAnalysis ?? record.impact_analysis;
  const impact = isRecord(impactRaw)
    ? {
        conflicts: asStringArray(impactRaw.conflicts),
        unstashedChanges: asBoolean(
          impactRaw.unstashedChanges ?? impactRaw.unstashed_changes,
          false,
        ),
        estimatedRisk: asString(
          impactRaw.estimatedRisk ?? impactRaw.estimated_risk,
          "unknown",
        ),
      }
    : null;

  return {
    commands: asObjectArray(record.commands).map(normalizeCommand),
    planSummary: asNullableString(record.planSummary ?? record.plan_summary),
    impactAnalysis: impact,
  };
}

function normalizeDecisionArchaeologyResponse(raw: unknown): TestingDecisionArchaeologyResponse {
  const record = isRecord(raw) ? raw : {};
  return {
    found: asBoolean(record.found, false),
    summary: asNullableString(record.summary),
    branchesTried: asStringArray(record.branchesTried ?? record.branches_tried),
    terminalCommands: asStringArray(record.terminalCommands ?? record.terminal_commands),
    confidence: asNumber(record.confidence, 0),
  };
}

export async function listProjects(
  token: string,
  backendUrl: string,
): Promise<TestingProjectSummary[]> {
  const payload = await requestJson<{ projects?: unknown[] }>(
    "/api/v1/projects",
    token,
    backendUrl,
    { method: "GET" },
  );

  if (!Array.isArray(payload.projects)) {
    return [];
  }

  return payload.projects.filter(isRecord).map((project) => ({
    id: asString(project.id),
    name: asString(project.name, "Untitled Project"),
    visibility: project.visibility === "team" ? "team" : "private",
    is_archived: asBoolean(project.is_archived, false),
  }));
}

export async function sendSnapshot(
  payload: TestingSnapshotPayload,
  token: string,
  backendUrl: string,
): Promise<TestingSnapshotResponse> {
  const response = await requestJson<UnknownRecord>(
    "/api/v1/snapshot",
    token,
    backendUrl,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );

  return {
    status: asString(response.status, "accepted"),
    message: asString(response.message, "Snapshot queued for processing."),
  };
}

export async function askQuery(
  question: string,
  token: string,
  backendUrl: string,
  projectId?: string,
): Promise<TestingQueryResponse> {
  const endpoint = shouldUsePmQueryEndpoint() ? "/api/v1/pm/query" : "/api/v1/query";
  const normalizedQuestion =
    projectId && !question.includes("Project scope hint:")
      ? `Project scope hint: ${projectId}\n\n${question}`
      : question;

  const response = await requestJson<UnknownRecord>(
    endpoint,
    token,
    backendUrl,
    {
      method: "POST",
      body: JSON.stringify({ question: normalizedQuestion }),
    },
  );

  return normalizeQueryResponse(response);
}

export async function getResurrectionPlan(
  target: string,
  token: string,
  backendUrl: string,
): Promise<TestingResurrectionResponse> {
  const response = await requestJson<UnknownRecord>(
    "/api/v1/resurrect",
    token,
    backendUrl,
    {
      method: "POST",
      body: JSON.stringify({ target }),
    },
  );

  return normalizeResurrectionResponse(response);
}

export async function getDecisionArchaeology(
  payload: TestingDecisionArchaeologyPayload,
  token: string,
  backendUrl: string,
): Promise<TestingDecisionArchaeologyResponse> {
  const response = await requestJson<UnknownRecord>(
    "/api/v1/decision-archaeology",
    token,
    backendUrl,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );

  return normalizeDecisionArchaeologyResponse(response);
}
