"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { DottedSurface } from "@/components/landing/DottedSurface";

export default function LandingPage() {
  const router = useRouter();
  const [showPmModal, setShowPmModal] = useState(false);
  const [pmEmail, setPmEmail] = useState("");
  const [pmPassword, setPmPassword] = useState("");
  const [pmError, setPmError] = useState("");
  const [isPmSubmitting, setIsPmSubmitting] = useState(false);
  const [queryLoading, setQueryLoading] = useState(false);
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "https://sc-backend-suhaan.azurewebsites.net";
  const extensionMarketplaceUrl = "https://marketplace.visualstudio.com/items?itemName=secondcortex-labs.secondcortex";
  const githubRepoUrl = "https://github.com/Syed-Suhaan/SecondCortex-Labs";
  const docsUrl = "https://github.com/Syed-Suhaan/SecondCortex-Labs/tree/main/docs";
  const mcpEndpointUrl = "https://sc-backend-suhaan.azurewebsites.net/mcp";
  const mainNavLinks = [
    { label: "Live Graph", href: "/live" },
    { label: "Team Cortex", href: "/?pm=true" },
    { label: "Thesis", href: "/thesis" },
    { label: "Offline Setup", href: "/offline-setup" },
    { label: "Architecture", href: "#arch" },
  ];
  const quickAccessFeatures = [
    {
      title: "Live Context Graph",
      description: "Open realtime context graph with timeline and team activity overlays.",
      href: "/live",
    },
    {
      title: "Team Cortex",
      description: "Track team progress, incident timelines, and compressed daily or weekly summaries from the PM surface.",
      href: "/?pm=true",
    },
    {
      title: "Decision Archaeology",
      description: "Hover over any function to see the full decision history behind it.",
      href: "#decision-archaeology",
    },
    {
      title: "SecondCortex Thesis",
      description: "Read the core thesis and product principles behind SecondCortex.",
      href: "/thesis",
    },
    {
      title: "Install Extension",
      description: "Install SecondCortex extension from VS Code Marketplace.",
      href: extensionMarketplaceUrl,
      external: true,
    },
    {
      title: "GitHub Repository",
      description: "Explore source code, releases, and implementation details.",
      href: githubRepoUrl,
      external: true,
    },
  ];

  const loginPmSession = async (email: string, password: string, guestMode: boolean) => {
    const res = await fetch(`${backendUrl}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Team Cortex login failed. Please check credentials.");
    }

    const data = await res.json();
    localStorage.setItem("sc_jwt_token", data.token);
    localStorage.setItem("sc_pm_mode", "auth");
    if (guestMode) {
      localStorage.setItem("sc_pm_guest_mode", "true");
      router.push("/live?pm=true&guest=true");
    } else {
      localStorage.removeItem("sc_pm_guest_mode");
      router.push("/live?pm=true");
    }
    setShowPmModal(false);
  };

  const handlePmGuestLogin = async () => {
    setIsPmSubmitting(true);
    setPmError("");

    // In local/demo workflows, bypass backend guest auth so mock Team Cortex always opens.
    if (typeof window !== "undefined" && ["localhost", "127.0.0.1"].includes(window.location.hostname)) {
      localStorage.setItem("sc_pm_mode", "auth");
      localStorage.setItem("sc_pm_guest_mode", "true");
      router.push("/live?pm=true&guest=true");
      setShowPmModal(false);
      setIsPmSubmitting(false);
      return;
    }

    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 45000);
    try {
      let res = await fetch(`${backendUrl}/api/v1/auth/pm-guest/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
      });

      if (res.status === 404) {
        res = await fetch(`${backendUrl}/api/v1/auth/pm_guest/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: controller.signal,
        });
      }

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Team Cortex guest login is unavailable right now.");
      }

      const data = await res.json();
      localStorage.setItem("sc_jwt_token", data.token);
      localStorage.setItem("sc_pm_mode", "auth");
      localStorage.setItem("sc_pm_guest_mode", "true");
      router.push("/live?pm=true&guest=true");
      setShowPmModal(false);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setPmError("Team Cortex guest login timed out. Please try again in a few seconds.");
      } else {
        setPmError(err instanceof Error ? err.message : "Team Cortex guest login failed.");
      }
    } finally {
      window.clearTimeout(timeoutId);
      setIsPmSubmitting(false);
    }
  };

  const handlePmLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const email = pmEmail.trim();
    if (!email || !pmPassword) {
      setPmError("Please enter both email and password.");
      return;
    }

    setIsPmSubmitting(true);
    setPmError("");

    try {
      await loginPmSession(email, pmPassword, false);
    } catch (err) {
      setPmError(err instanceof Error ? err.message : "Cannot reach backend. Check your network and try again.");
    } finally {
      setIsPmSubmitting(false);
    }
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("pm") === "true") {
      setPmError("");
      setShowPmModal(true);
    }
  }, []);

  useEffect(() => {
    const queryBtn = document.getElementById("query-btn");
    const queryInput = document.getElementById("query-input") as HTMLInputElement | null;
    const resultText = document.getElementById("result-text");
    const resultLabel = document.querySelector(".result-label");
    const queryResult = document.getElementById("query-result");

    if (!queryBtn || !queryInput || !resultText || !resultLabel || !queryResult) {
      return;
    }

    const timers: number[] = [];

    const animateCounters = () => {
      document.querySelectorAll<HTMLElement>("[data-target]").forEach((el) => {
        const target = Number.parseInt(el.dataset.target ?? "", 10);
        if (Number.isNaN(target)) {
          return;
        }
        const suffix = el.dataset.suffix ?? "";
        let start = 0;
        const dur = 1600;
        const step = (ts: number) => {
          if (!start) {
            start = ts;
          }
          const p = Math.min((ts - start) / dur, 1);
          const ease = 1 - (1 - p) ** 3;
          el.textContent = `${Math.round(ease * target)}${suffix}`;
          if (p < 1) {
            requestAnimationFrame(step);
          }
        };
        requestAnimationFrame(step);
      });
    };

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
            if (entry.target.classList.contains("stats-bar")) {
              animateCounters();
            }
          }
        });
      },
      { threshold: 0.1 },
    );
    document.querySelectorAll(".reveal").forEach((el) => observer.observe(el));

    const responses: Record<string, { label: string; text: string }> = {
      "src/payment/processor.ts": {
        label: "Retriever - Team Match - src/payment/processor.ts",
        text: "Branch: feat/payment-v2 - 2 hours ago\n\nContext: Retry limit reduced from 5 to 3 to avoid exponential backoff storm under concurrent load. Marked with FIXME to revisit after load testing.\n\nEvidence: payment.test.ts failures + staging alert @ 14:43.",
      },
      "src/auth/tokenRefresh.ts": {
        label: "Retriever - Team Match - src/auth/tokenRefresh.ts",
        text: "Branch: feat/auth-fix - 5 hours ago\n\nContext: Token queue chosen over mutex lock to reduce latency under concurrent expiry requests. Mutex approach added ~40ms p99 in local benchmarks.",
      },
      "semanticFirewall.ts": {
        label: "Retriever - Team Match - semanticFirewall.ts",
        text: "Branch: feat/security - 1 day ago\n\nContext: AST-based secret detection implemented with TypeScript Compiler API. Regex fallback catches keys, JWTs, bearer tokens, and private key formats.",
      },
      "agents/simulator.py": {
        label: "Retriever - Team Match - agents/simulator.py",
        text: "Branch: feat/simulator - 2 days ago\n\nContext: Simulator pre-flight checks detect unstashed files, branch conflicts, and in-flight process interruptions before Executor actions.",
      },
      "services/vector_db.py": {
        label: "Retriever - Team Match - services/vector_db.py",
        text: "Branch: main - 3 days ago\n\nContext: Team retrieval supports ChromaDB personal namespace + Azure AI Search team namespace with semantic similarity and metadata-scoped filtering.",
      },
    };

    const queryMap: Record<string, string> = {
      "why was retry limit reduced": "src/payment/processor.ts",
      "token refresh race condition fix": "src/auth/tokenRefresh.ts",
      "what is prateek working on": "src/payment/processor.ts",
      "what caused yesterday's incident": "src/payment/processor.ts",
      "where are secrets handled": "semanticFirewall.ts",
    };

    const memEntries = document.querySelectorAll<HTMLElement>(".mem-entry");
    const setResult = (label: string, text: string) => {
      resultLabel.textContent = label;
      resultText.style.opacity = "0";
      const timerId = window.setTimeout(() => {
        resultText.textContent = text;
        resultText.style.opacity = "1";
      }, 200);
      timers.push(timerId);
    };

    let isQueryLoading = false;
    const setQueryLoadingState = (isLoading: boolean) => {
      isQueryLoading = isLoading;
      setQueryLoading(isLoading);
      queryResult.classList.toggle("loading", isLoading);
    };

    const fireQuery = (q: string) => {
      const normalized = q.toLowerCase().trim();
      if (!normalized || isQueryLoading) {
        return;
      }

      setQueryLoadingState(true);
      setResult("Retriever - Searching...", `Searching vector store for: "${q}"\n\nRunning semantic retrieval...`);

      const timerId = window.setTimeout(() => {
        const match = queryMap[normalized];
        if (match) {
          memEntries.forEach((e) => {
            e.classList.remove("active");
            if (e.dataset.file === match) {
              e.classList.add("active");
            }
          });
          const response = responses[match];
          if (response) {
            setResult(response.label, response.text);
          }
        } else {
          setResult(
            "Retriever - Semantic Search",
            `Searching vector store for: "${q}"\n\nRunning cosine similarity search across ${Math.floor(Math.random() * 800) + 200} stored snapshots...\n\nTop result: similarity score 0.${Math.floor(Math.random() * 15) + 80} - context match found in active workspace history.`,
          );
        }
        setQueryLoadingState(false);
      }, 600);
      timers.push(timerId);
    };

    const memHandlers: Array<{ el: HTMLElement; fn: EventListener }> = [];
    memEntries.forEach((entry) => {
      const fn = () => {
        memEntries.forEach((e) => e.classList.remove("active"));
        entry.classList.add("active");
        const file = entry.dataset.file;
        if (!file) {
          return;
        }
        const response = responses[file];
        if (response) {
          setResult(response.label, response.text);
        }
      };
      entry.addEventListener("click", fn);
      memHandlers.push({ el: entry, fn });
    });

    const suggestionChips = document.querySelectorAll<HTMLElement>(".suggestion-chip");
    const chipHandlers: Array<{ el: HTMLElement; fn: EventListener }> = [];
    suggestionChips.forEach((chip) => {
      const fn = () => {
        const q = chip.dataset.query ?? chip.textContent ?? "";
        queryInput.value = q;
        fireQuery(q);
      };
      chip.addEventListener("click", fn);
      chipHandlers.push({ el: chip, fn });
    });

    const onQueryClick = () => fireQuery(queryInput.value);
    const onQueryKey = (e: KeyboardEvent) => {
      if (e.key === "Enter") {
        fireQuery(queryInput.value);
      }
    };
    queryBtn.addEventListener("click", onQueryClick);
    queryInput.addEventListener("keydown", onQueryKey);

    return () => {
      timers.forEach((t) => clearTimeout(t));
      observer.disconnect();
      memHandlers.forEach(({ el, fn }) => el.removeEventListener("click", fn));
      chipHandlers.forEach(({ el, fn }) => el.removeEventListener("click", fn));
      queryBtn.removeEventListener("click", onQueryClick);
      queryInput.removeEventListener("keydown", onQueryKey);
    };
  }, []);

  return (
    <>
      <nav>
        <div className="nav-logo">
          Second<span>Cortex</span>
        </div>
        <ul className="nav-links">
          {mainNavLinks.map((item) => (
            <li key={item.label}>
              <a href={item.href}>{item.label}</a>
            </li>
          ))}
        </ul>
        <div className="nav-actions">
          <button
            className="nav-login nav-pm-login"
            type="button"
            onClick={() => {
              setPmError("");
              setShowPmModal(true);
            }}
          >
            Team Cortex
          </button>
          <a className="nav-login" href="/thesis">
            Thesis
          </a>
          <a className="nav-login" href="/login">
            Login
          </a>
          <a className="nav-cta" href={extensionMarketplaceUrl} target="_blank" rel="noreferrer">
            Install Extension -&gt;
          </a>
        </div>
      </nav>

      <section className="hero">
        <DottedSurface />

        <div className="hero-content hero-content-centered">
          <h1 className="hero-title hero-title-premium">Neither You Nor Your AI Agents Will Lose Context.</h1>
          <p className="hero-sub">
            Securely captured, intelligently stored, instantly retrievable for you and your AI.
          </p>
          <div className="hero-actions">
            <a className="btn-primary btn-large" href={extensionMarketplaceUrl} target="_blank" rel="noreferrer">
              Install on VS Code
            </a>
            <a className="btn-secondary btn-large" href={docsUrl} target="_blank" rel="noreferrer">
              Read the Docs
            </a>
          </div>
        </div>
      </section>

      <div className="ticker-wrap">
        <div className="ticker-track" id="ticker-track">
          <span className="ticker-item">Semantic Firewall</span>
          <span className="ticker-item">PowerSync Realtime Sync</span>
          <span className="ticker-item">ChromaDB + Azure AI Search</span>
          <span className="ticker-item">Decision Archaeology</span>
          <span className="ticker-item">Incident Reconstruction</span>
          <span className="ticker-item">MCP SSE Server</span>
          <span className="ticker-item">GPT-4o Planner</span>
          <span className="ticker-item">Groq Executor</span>
          <span className="ticker-item">Simulator Safety Report</span>
          <span className="ticker-item">VS Code Extension</span>
          <span className="ticker-item">Semantic Retrieval</span>
          <span className="ticker-item">Team Context Graph</span>
          <span className="ticker-item">Azure App Service</span>
          <span className="ticker-item">Semantic Firewall</span>
          <span className="ticker-item">PowerSync Realtime Sync</span>
          <span className="ticker-item">ChromaDB + Azure AI Search</span>
          <span className="ticker-item">Decision Archaeology</span>
          <span className="ticker-item">Incident Reconstruction</span>
          <span className="ticker-item">MCP SSE Server</span>
          <span className="ticker-item">GPT-4o Planner</span>
          <span className="ticker-item">Groq Executor</span>
          <span className="ticker-item">Simulator Safety Report</span>
          <span className="ticker-item">VS Code Extension</span>
          <span className="ticker-item">Semantic Retrieval</span>
          <span className="ticker-item">Team Context Graph</span>
          <span className="ticker-item">Azure App Service</span>
        </div>
      </div>

      <div className="stats-bar reveal">
        <div className="stat-item">
          <div className="stat-num" data-target="41536">
            0
          </div>
          <div className="stat-label">Snapshots Indexed</div>
        </div>
        <div className="stat-item">
          <div className="stat-num" data-target="55">
            0
          </div>
          <div className="stat-label">Top In Microsoft AI Unlocked</div>
        </div>
        <div className="stat-item">
          <div className="stat-num" data-target="2" data-suffix="s">
            0
          </div>
          <div className="stat-label">Typical Retrieval</div>
        </div>
        <div className="stat-item">
          <div className="stat-num" data-target="15" data-suffix="+">
            0+
          </div>
          <div className="stat-label">MCP Tools</div>
        </div>
        <div className="stat-item">
          <div className="stat-num" data-target="1536">
            0
          </div>
          <div className="stat-label">Embedding Dimensions</div>
        </div>
      </div>

      <section id="feature-access" className="feature-access-section reveal">
        <div className="section-label">Quick Access</div>
        <div className="section-title">
          Recently shipped
          <br />
          <em>feature shortcuts.</em>
        </div>
        <p className="section-desc">
          Recently shipped feature shortcuts.
        </p>

        <div className="feature-access-grid">
          {quickAccessFeatures.map((feature) => (
            <a
              key={feature.title}
              className="feature-access-card"
              href={feature.href}
              target={feature.external ? "_blank" : undefined}
              rel={feature.external ? "noreferrer" : undefined}
            >
              <div className="feature-access-title">{feature.title}</div>
              <div className="feature-access-desc">{feature.description}</div>
              <span className="feature-access-cta">Open -&gt;</span>
            </a>
          ))}
        </div>
      </section>

      <section id="how">
        <div className="section-label">How it works</div>
        <div className="section-title">
          From keystroke to
          <br />
          <em>memory</em> in milliseconds.
        </div>
        <p className="section-desc reveal">
          IDE events are captured locally, passed through a privacy-first Semantic Firewall, embedded into vector
          memory, and exposed to any AI agent via MCP so your tools finally know why your code looks the way it does.
        </p>

        <div className="pipeline reveal">
          <div className="pipeline-track" />
          <div className="pipeline-nodes">
            <div className="pipeline-node">
              <div className="node-index">01</div>
              <div className="node-title">Capture</div>
              <div className="node-desc">
                The VS Code extension monitors every IDE event: open tabs, active files, terminal commands, git state,
                code comments, diagnostics, function signatures, and debug sessions with a debounced snapshot system.
              </div>
              <span className="node-tag">eventCapture.ts</span>
            </div>
            <div className="pipeline-node">
              <div className="node-index">02</div>
              <div className="node-title">Firewall</div>
              <div className="node-desc">
                Every snapshot passes through Semantic Firewall before upload. AST-level analysis with TypeScript
                Compiler API detects tokens and credentials; regex fallback catches format-matched secrets.
              </div>
              <span className="node-tag">semanticFirewall.ts</span>
            </div>
            <div className="pipeline-node">
              <div className="node-index">03</div>
              <div className="node-title">Embed + Sync</div>
              <div className="node-desc">
                Sanitized snapshots are vectorized using text-embedding-3-small (1536d) and stored in personal memory.
                PowerSync syncs snapshots to the team backend in real-time with offline queue + replay support.
              </div>
              <span className="node-tag">vector_db.py</span>
            </div>
            <div className="pipeline-node">
              <div className="node-index">04</div>
              <div className="node-title">Retrieve</div>
              <div className="node-desc">
                When you ask a question or trigger restore, Retriever searches by semantic similarity across personal
                history and team context to return not just code, but decisions and failed branches.
              </div>
              <span className="node-tag">retriever.py</span>
            </div>
            <div className="pipeline-node">
              <div className="node-index">05</div>
              <div className="node-title">Execute</div>
              <div className="node-desc">
                After confirmation, Executor applies the plan to your workspace: opening files, switching branches, and
                running commands. Simulator runs a pre-flight safety check before touching anything.
              </div>
              <span className="node-tag">executor.py</span>
            </div>
          </div>
        </div>
      </section>

      <div className="glow-line" />

      <section id="agents" className="agents-section">
        <div className="section-label">The agents</div>
        <div className="section-title">
          Four agents.
          <br />
          <em>One pipeline.</em>
        </div>
        <p className="section-desc reveal">
          A focused multi-agent architecture where each component has a distinct role. Every agent has a circuit
          breaker (`max_steps=3`) to prevent infinite loops.
        </p>

        <div className="agents-grid reveal agents-grid-three">
          <div className="agent-card">
            <div className="agent-icon">
              <div className="agent-icon-inner agent-code">PLN</div>
            </div>
            <div className="agent-name">Planner</div>
            <div className="agent-role">Task Decomposition</div>
            <div className="agent-desc">
              Takes a natural language request and breaks it into a structured action plan. Interprets developer
              intent, creates parallel search tasks, and routes retrieval scope (personal, team, cross-repo).
            </div>
            <div className="agent-spec">
              <div className="spec-item">LLM: GPT-4o via Azure OpenAI</div>
              <div className="spec-item">Output: Structured action plan with search tasks</div>
              <div className="spec-item">Requires explicit user confirmation</div>
            </div>
          </div>
          <div className="agent-card">
            <div className="agent-icon">
              <div className="agent-icon-inner agent-code">RTV</div>
            </div>
            <div className="agent-name">Retriever</div>
            <div className="agent-role">Semantic Memory Search</div>
            <div className="agent-desc">
              Searches vector memory via cosine similarity to surface relevant history: files, branches, decisions,
              terminal commands, comments, and incidents. Exposed as MCP for any compatible AI agent.
            </div>
            <div className="agent-spec">
              <div className="spec-item">Store: ChromaDB or Azure AI Search (team mode)</div>
              <div className="spec-item">Embeddings: text-embedding-3-small (1536d)</div>
              <div className="spec-item">Exposed via MCP SSE endpoint with 15+ tools</div>
            </div>
          </div>
          <div className="agent-card">
            <div className="agent-icon">
              <div className="agent-icon-inner agent-code">EXC</div>
            </div>
            <div className="agent-name">Executor</div>
            <div className="agent-role">Workspace Restoration</div>
            <div className="agent-desc">
              Applies approved action plan to your VS Code workspace: opening files, switching branches, restoring
              terminal context. Runs the Simulator first to check for unstashed changes and conflicts.
            </div>
            <div className="agent-spec">
              <div className="spec-item">LLM: Groq Llama-3.1-8b (fast inference)</div>
              <div className="spec-item">Sub-agent: Simulator (git pre-flight safety checks)</div>
              <div className="spec-item">PowerShell + bash compatible</div>
            </div>
          </div>
          <div className="agent-card">
            <div className="agent-icon">
              <div className="agent-icon-inner agent-code">SIM</div>
            </div>
            <div className="agent-name">Simulator</div>
            <div className="agent-role">Pre-Flight Safety</div>
            <div className="agent-desc">
              Runs before every Executor action. Detects unstashed files, branch conflicts, uncommitted changes, and
              running processes that would be interrupted. Blocks execution on unresolved conflicts.
            </div>
            <div className="agent-spec">
              <div className="spec-item">Input: Proposed plan + current git state</div>
              <div className="spec-item">Output: Safety report with conflict detection</div>
              <div className="spec-item">Hard block on unresolved risks</div>
            </div>
          </div>
        </div>
      </section>

      <section id="memory" className="memory-demo">
        <div className="section-label">Live Memory</div>
        <div className="section-title">
          Query your past work
          <br />
          <em>and your team&apos;s.</em>
        </div>

        <div className="demo-split reveal">
          <div className="memory-visualizer">
            <div className="memory-header">
              <span>ChromaDB / Azure AI Search - Team Namespace</span>
              <span className="mem-status">LIVE - 2 members - 24 snapshots indexed</span>
            </div>
            <div className="memory-entries" id="mem-entries">
              <div className="mem-entry active" data-file="src/payment/processor.ts" data-branch="feat/payment-v2" data-time="2h ago">
                <div className="mem-file">src/payment/processor.ts</div>
                <div className="mem-summary">
                  Reduced retry limit from 5 to 3. Decision context: cascade failure risk at higher values under concurrent load.
                </div>
                <div className="mem-meta">
                  <span>feat/payment-v2</span>
                  <span>2h ago</span>
                </div>
              </div>
              <div className="mem-entry" data-file="src/auth/tokenRefresh.ts" data-branch="feat/auth-fix" data-time="5h ago">
                <div className="mem-file">src/auth/tokenRefresh.ts</div>
                <div className="mem-summary">
                  Implemented token queue pattern to resolve race condition when two requests hit expiry simultaneously.
                </div>
                <div className="mem-meta">
                  <span>feat/auth-fix</span>
                  <span>5h ago</span>
                </div>
              </div>
              <div className="mem-entry" data-file="semanticFirewall.ts" data-branch="feat/security" data-time="1d ago">
                <div className="mem-file">semanticFirewall.ts</div>
                <div className="mem-summary">
                  Added AST-level detection for TypeScript Compiler API variable-name patterns with regex fallback.
                </div>
                <div className="mem-meta">
                  <span>feat/security</span>
                  <span>1d ago</span>
                </div>
              </div>
              <div className="mem-entry" data-file="agents/simulator.py" data-branch="feat/simulator" data-time="2d ago">
                <div className="mem-file">agents/simulator.py</div>
                <div className="mem-summary">Pre-flight simulator generates conflict safety reports from git diff before Executor runs.</div>
                <div className="mem-meta">
                  <span>feat/simulator</span>
                  <span>2d ago</span>
                </div>
              </div>
              <div className="mem-entry" data-file="services/vector_db.py" data-branch="main" data-time="3d ago">
                <div className="mem-file">services/vector_db.py</div>
                <div className="mem-summary">Team retrieval supports ChromaDB + Azure AI Search with scoped semantic search.</div>
                <div className="mem-meta">
                  <span>main</span>
                  <span>3d ago</span>
                </div>
              </div>
            </div>
          </div>

          <div className="query-panel">
            <div className="query-title">Ask your second cortex anything about your codebase.</div>
            <div className="query-desc">
              Natural language semantic search across your entire development history and your team&apos;s. Not just grep, but decisions.
            </div>

            <div className="query-input-wrap">
              <input className="query-input" id="query-input" type="text" placeholder="why was retry limit reduced" />
              <button className={`query-btn ${queryLoading ? "is-loading" : ""}`} id="query-btn" type="button" disabled={queryLoading}>
                {queryLoading ? (
                  <>
                    <span className="loading-ring" aria-hidden="true" />
                    Searching...
                  </>
                ) : (
                  "SEARCH"
                )}
              </button>
            </div>

            <div>
              <div className="query-try">Try asking:</div>
              <div className="query-suggestions">
                <div className="suggestion-chip" data-query="why was retry limit reduced">
                  why was retry limit reduced
                </div>
                <div className="suggestion-chip" data-query="token refresh race condition fix">
                  token refresh race condition fix
                </div>
                <div className="suggestion-chip" data-query="what is prateek working on">
                  what is Prateek working on
                </div>
                <div className="suggestion-chip" data-query="what caused yesterday's incident">
                  what caused yesterday&apos;s incident
                </div>
                <div className="suggestion-chip" data-query="where are secrets handled">
                  where are secrets handled
                </div>
              </div>
            </div>

            <div className="query-result" id="query-result" aria-live="polite">
              <div className="result-label">Retriever - Awaiting Query</div>
              <div className="result-text" id="result-text">
                Click a memory entry or type a question to retrieve decision history from personal and team memory.
              </div>
            </div>
          </div>
        </div>
      </section>
<section id="security" className="security-section">
        <div className="section-label">Security</div>
        <div className="section-title">
          Your secrets stay
          <br />
          <em>yours.</em>
        </div>
        <p className="section-desc reveal">
          Your secrets stay yours by architecture, not policy. Every snapshot is sanitized locally before upload and every execution path requires confirmation.
        </p>

        <div className="security-grid reveal">
          <div className="security-card">
            <div className="security-title">Semantic Firewall (Local)</div>
            <div className="security-text">
              AST-level analysis + regex fallback detect API keys, JWTs, bearer tokens, Stripe keys, OpenAI keys, and private key formats before data leaves your machine.
            </div>
          </div>
          <div className="security-card">
            <div className="security-title">Local-First Storage</div>
            <div className="security-text">
              Snapshots write to local SQLite first via PowerSync. If SecondCortex shuts down, your memory still lives locally in a standard database.
            </div>
          </div>
          <div className="security-card">
            <div className="security-title">Per-User + Per-Team Isolation</div>
            <div className="security-text">
              Personal memory uses per-user namespace isolation. Team memory uses team_id-scoped filtering in Azure AI Search to prevent cross-team leakage.
            </div>
          </div>
          <div className="security-card">
            <div className="security-title">Confirmation Before Execution</div>
            <div className="security-text">
              Executor never runs without your sign-off. Simulator runs a safety check first and destructive operations always require explicit confirmation.
            </div>
          </div>
          <div className="security-card">
            <div className="security-title">Offline Mode Available</div>
            <div className="security-text">
              Full local mode uses LanceDB + Nomic Embed for zero cloud dependency and zero network calls in regulated or air-gapped environments.
            </div>
          </div>
        </div>
      </section>
<section id="decision-archaeology" className="memory-demo">
        <div className="section-label">Decision Archaeology</div>
        <div className="section-title">
          Every function remembers
          <br />
          <em>why it was written.</em>
        </div>

        <div className="demo-split reveal">
          <div className="query-result">
            <div className="result-label">handleTokenExpiry() - Decision History</div>
            <div className="result-text">
              Last changed by Prateek - March 14 - &quot;fix: resolve concurrent refresh race&quot;

              Why this approach: Token queue pattern selected over mutex lock to avoid latency penalty under concurrent requests.

              Branches tried: feat/mutex-lock to feat/token-queue (current)

              Key commands: jest --watch auth.test.ts, ab -n 1000 -c 50 /auth/refresh

              Context confidence: 94% | Evidence: git commit a3f4b2c, snapshot snap_2891
            </div>
          </div>

          <div className="query-panel">
            <div className="query-title">Hover over any function in VS Code.</div>
            <div className="query-desc">
              SecondCortex surfaces branches tried, approaches abandoned, and reasoning behind each architectural choice via git blame + vector memory + GPT-4o synthesis.
            </div>
          </div>
        </div>
      </section>

      <section id="incident-reconstruction" className="arch-section">
        <div className="section-label">Incident Reconstruction</div>
        <div className="section-title">
          40 minutes of incident reconstruction.
          <br />
          <em>30 seconds.</em>
        </div>

        <div className="arch-diagram reveal">
          <div className="arch-header">cortex investigate --incident --window 48h</div>
          <div className="query-result">
            <div className="result-text">
              Team: SecondCortex Labs - 2 developers

              14:32  Prateek  feat/payment-v2  processor.ts +47 -12
              14:33  Prateek  Comment: reducing retry from 5 to 3, cascade risk
              14:38  Saketh   docker push to staging deploy
              14:41  Tests    3 failing: payment.test.ts
              14:43  Prateek  commit: fix: reduce retry limit 5 to 3
              14:43  Monitor  ALERT: staging response time &gt;5000ms
              14:44  Monitor  ALERT: staging down

              Root cause: Retry reduction triggered backoff storm under concurrent load.
              Edge case was not covered in test suite.
            </div>
          </div>
        </div>
      </section>

      <section id="arch" className="arch-section">
        <div className="section-label">Architecture</div>
        <div className="section-title">
          Production-grade
          <br />
          <em>from day one.</em>
        </div>

        <div className="arch-diagram reveal">
          <div className="arch-header">System Architecture Overview</div>

          <div className="arch-row">
            <div className="arch-box highlight">Capture Layer: VS Code Extension (TypeScript)</div>
            <div className="arch-arrow">-&gt;</div>
            <div className="arch-box">Event Capture + Debouncer (30s threshold)</div>
            <div className="arch-arrow">-&gt;</div>
            <div className="arch-box">Semantic Firewall (AST + Regex, local)</div>
          </div>

          <div className="arch-sep" />

          <div className="arch-row">
            <div className="arch-box primary">Intelligence Layer: FastAPI Backend</div>
            <div className="arch-arrow">-&gt;</div>
            <div className="arch-box">4-Operation Router (ADD/UPDATE/DELETE/NOOP)</div>
            <div className="arch-arrow">-&gt;</div>
            <div className="arch-box">4-Agent Pipeline (Planner -&gt; Retriever -&gt; Executor -&gt; Simulator)</div>
          </div>

          <div className="arch-sep" />

          <div className="arch-row">
            <div className="arch-box">Memory Layer: ChromaDB + Azure AI Search + LanceDB</div>
            <div className="arch-arrow">-&gt;</div>
            <div className="arch-box">Sync: PowerSync (SQLite &lt;-&gt; Azure Postgres)</div>
            <div className="arch-arrow">-&gt;</div>
            <div className="arch-box highlight">Embeddings: text-embedding-3-small (1536d)</div>
          </div>

          <div className="arch-sep" />

          <div className="arch-row">
            <div className="arch-box">Integration Layer: MCP SSE Server (/mcp)</div>
            <div className="arch-arrow">-&gt;</div>
            <div className="arch-box">15+ tools: search_memory, get_context_for_task, get_function_context, get_raw_snapshots</div>
          </div>

          <div className="arch-sep" />

          <div className="arch-row">
            <div className="arch-box">Presentation Layer: Next.js 15 Frontend</div>
            <div className="arch-arrow">+</div>
            <div className="arch-box">Deployment: GitHub Actions + GHCR Docker + Azure App Service</div>
            <div className="arch-label">10 production deployments shipped</div>
          </div>
        </div>
      </section>

      <section id="mcp" className="memory-demo">
        <div className="section-label">MCP Integration</div>
        <div className="section-title">
          Every AI agent gets
          <br />
          <em>your memory.</em>
        </div>

        <div className="demo-split reveal">
          <div className="query-result">
            <div className="result-label">MCP Server Config</div>
            <div className="result-text">{`{
  "tools": {
    "mcp": {
      "servers": {
        "secondcortex": {
          "url": "https://sc-backend-suhaan.azurewebsites.net/mcp",
          "transport": "sse"
        }
      }
    }
  }
}`}</div>
          </div>
          <div className="query-panel">
            <div className="query-title">Claude Code, Cursor, GitHub Copilot, PicoClaw.</div>
            <div className="query-desc">
              Any MCP-compatible agent can query your codebase decisions, debugging history, and team institutional context without you manually pasting context.
            </div>
            <a className="btn-secondary btn-large" href={mcpEndpointUrl} target="_blank" rel="noreferrer">
              Open MCP Endpoint
            </a>
          </div>
        </div>
      </section>

      <section id="team-memory" className="agents-section">
        <div className="section-label">Team Memory</div>
        <div className="section-title">
          Institutional knowledge
          <br />
          <em>that survives.</em>
        </div>
        <p className="section-desc reveal">
          Every decision from every developer becomes queryable forever. New engineer onboarding, leave coverage, and 2am incident triage all benefit from persistent shared context.
        </p>
      </section>
      <section className="cta-section">
        <div className="cta-glow" />
        <p className="section-label cta-label">Call To Action</p>
        <h2 className="cta-title">
          Build with context.
          <br />
          <em>Ship with confidence.</em>
        </h2>
        <p className="cta-sub">
          Install the VS Code extension. SecondCortex starts building your memory immediately. Selected Top 55 of
          10,000+ in Microsoft AI Unlocked.
        </p>
        <div className="cta-actions">
          <a className="btn-primary btn-large" href={extensionMarketplaceUrl} target="_blank" rel="noreferrer">
            Install Extension - Free
          </a>
          <a className="btn-secondary btn-large" href={githubRepoUrl} target="_blank" rel="noreferrer">
            View on GitHub
          </a>
        </div>
      </section>

      <footer>
        <div className="nav-logo">
          Second<span>Cortex</span>
        </div>

        <div className="footer-links-group">
          <div className="footer-links-title">Product</div>
          <div className="footer-links">
            <a href="#how">How It Works</a>
            <a href="#agents">Agents</a>
            <a href="#decision-archaeology">Decision Archaeology</a>
            <a href="#incident-reconstruction">Incident Reconstruction</a>
            <a href="#team-memory">Team Memory</a>
            <a href="#security">Security</a>
          </div>
        </div>

        <div className="footer-links-group">
          <div className="footer-links-title">Access</div>
          <div className="footer-links">
            <a href="/login">Login</a>
            <a href="/signup">Sign Up</a>
            <a href="/live">Live Graph</a>
            <a href="/thesis">Thesis</a>
            <button
              type="button"
              className="footer-link-button"
              onClick={() => {
                setPmError("");
                setShowPmModal(true);
              }}
            >
              Team Cortex
            </button>
            <a href="/offline-setup">Offline Setup</a>
          </div>
        </div>

        <div className="footer-links-group">
          <div className="footer-links-title">Resources</div>
          <div className="footer-links">
            <a href={githubRepoUrl} target="_blank" rel="noreferrer">GitHub</a>
            <a href={extensionMarketplaceUrl} target="_blank" rel="noreferrer">VS Code Marketplace</a>
            <a href={docsUrl} target="_blank" rel="noreferrer">Documentation</a>
            <a href="/thesis">Thesis</a>
            <a href="/offline-setup">Offline Setup</a>
            <a href="#arch">Architecture</a>
            <a href="#mcp">MCP Integration Guide</a>
            <a href="https://docs.trychroma.com/" target="_blank" rel="noreferrer">ChromaDB Docs</a>
            <a href="https://ollama.com/" target="_blank" rel="noreferrer">Ollama</a>
          </div>
        </div>

        <div>Copyright 2026 SecondCortex Labs</div>
      </footer>

      {showPmModal && (
        <div className="sc-modal-wrap">
          <div className="sc-modal-backdrop" onClick={() => setShowPmModal(false)} />
          <div className="sc-modal-card pm-login-card">
            <div className="sc-auth-header">
              <p className="sc-auth-eyebrow">Team Cortex Access</p>
              <h2 className="sc-auth-title">Team Cortex Login</h2>
              <p className="sc-auth-sub">Log in to Team Cortex or continue with guest access to review team progress.</p>
            </div>

            <form onSubmit={handlePmLogin} className="sc-auth-form">
              <label className="sc-auth-label" htmlFor="pm-email">
                Email
              </label>
              <input
                id="pm-email"
                className="sc-auth-input"
                type="email"
                value={pmEmail}
                onChange={(event) => setPmEmail(event.target.value)}
                placeholder="pm@secondcortex.ai"
                required
              />

              <label className="sc-auth-label" htmlFor="pm-password">
                Password
              </label>
              <input
                id="pm-password"
                className="sc-auth-input"
                type="password"
                value={pmPassword}
                onChange={(event) => setPmPassword(event.target.value)}
                placeholder="********"
                required
              />

              {pmError && <div className="sc-auth-error" aria-live="polite">{pmError}</div>}

              <button type="submit" disabled={isPmSubmitting} className="btn-primary sc-auth-submit">
                {isPmSubmitting ? (
                  <>
                    <span className="loading-ring" aria-hidden="true" />
                    Please wait…
                  </>
                ) : (
                  "Enter Team Cortex"
                )}
              </button>

              <button
                type="button"
                className="btn-secondary sc-auth-submit sc-guest-btn"
                disabled={isPmSubmitting}
                onClick={handlePmGuestLogin}
              >
                {isPmSubmitting ? (
                  <>
                    <span className="loading-ring" aria-hidden="true" />
                    Please wait…
                  </>
                ) : (
                  "Team Cortex Guest Login"
                )}
              </button>
            </form>
          </div>
        </div>
      )}
    </>
  );
}



