"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

type TerminalLine = {
  type: "cmd" | "out" | "highlight" | "warn" | "success";
  prompt?: string;
  text: string;
};

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
  const mainNavLinks = [
    { label: "Live Graph", href: "/live" },
    { label: "PM Dashboard", href: "/live?pm=true" },
    { label: "Testing", href: "/testing" },
    { label: "Architecture", href: "#arch" },
  ];
  const quickAccessFeatures = [
    {
      title: "Live Context Graph",
      description: "Open realtime context graph with timeline and retrieval overlays.",
      href: "/live",
    },
    {
      title: "PM Dashboard",
      description: "Track team progress and summaries from a manager view.",
      href: "/live?pm=true",
    },
    {
      title: "Testing Playground",
      description: "Access the internal testing routes and validation screens.",
      href: "/testing",
    },
    {
      title: "Install Extension",
      description: "Install SecondCortex extension from VS Code Marketplace.",
      href: extensionMarketplaceUrl,
      external: true,
    },
    {
      title: "Sign Up",
      description: "Create account and start capturing memory in your workspace.",
      href: "/signup",
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
      throw new Error(err.detail || "PM login failed. Please check credentials.");
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
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 45000);
    try {
      const res = await fetch(`${backendUrl}/api/v1/auth/pm-guest/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Guest PM login is unavailable right now.");
      }

      const data = await res.json();
      localStorage.setItem("sc_jwt_token", data.token);
      localStorage.setItem("sc_pm_mode", "auth");
      localStorage.setItem("sc_pm_guest_mode", "true");
      router.push("/live?pm=true&guest=true");
      setShowPmModal(false);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setPmError("Guest PM login timed out. Please try again in a few seconds.");
      } else {
        setPmError(err instanceof Error ? err.message : "Guest PM login failed.");
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
    const canvas = document.getElementById("neural-canvas") as HTMLCanvasElement | null;
    const tb = document.getElementById("terminal-body");
    const queryBtn = document.getElementById("query-btn");
    const queryInput = document.getElementById("query-input") as HTMLInputElement | null;
    const resultText = document.getElementById("result-text");
    const resultLabel = document.querySelector(".result-label");
    const queryResult = document.getElementById("query-result");

    if (!canvas || !tb || !queryBtn || !queryInput || !resultText || !resultLabel || !queryResult) {
      return;
    }

    let disposed = false;
    let canvasRaf = 0;
    const timers: number[] = [];
    const intervals: number[] = [];

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }

    type NodePoint = { x: number; y: number; vx: number; vy: number; r: number };
    const nodes: NodePoint[] = [];
    const resize = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    };
    resize();
    window.addEventListener("resize", resize);

    for (let i = 0; i < 60; i += 1) {
      nodes.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        r: Math.random() * 2 + 1,
      });
    }

    const drawCanvas = () => {
      if (disposed) {
        return;
      }
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      nodes.forEach((n) => {
        n.x += n.vx;
        n.y += n.vy;
        if (n.x < 0 || n.x > canvas.width) {
          n.vx *= -1;
        }
        if (n.y < 0 || n.y > canvas.height) {
          n.vy *= -1;
        }
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(255,255,255,0.35)";
        ctx.fill();
      });

      nodes.forEach((a, i) => {
        nodes.slice(i + 1).forEach((b) => {
          const d = Math.hypot(a.x - b.x, a.y - b.y);
          if (d < 120) {
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.strokeStyle = `rgba(255,255,255,${0.1 * (1 - d / 120)})`;
            ctx.lineWidth = 0.5;
            ctx.stroke();
          }
        });
      });
      canvasRaf = requestAnimationFrame(drawCanvas);
    };
    drawCanvas();

    const lines: TerminalLine[] = [
      { type: "cmd", prompt: "~", text: "cortex resurrect --branch feat/auth" },
      { type: "out", text: "Scanning vector store..." },
      { type: "out", text: "Found 3 matching snapshots" },
      { type: "out", text: "" },
      { type: "out", text: "Proposed Action Plan:" },
      { type: "highlight", text: "1. Open auth/jwt_handler.py" },
      { type: "highlight", text: "2. Restore 4 tabs from last session" },
      { type: "highlight", text: "3. Switch to branch: feat/auth" },
      { type: "out", text: "" },
      { type: "warn", text: "Simulator: 1 unstashed file detected" },
      { type: "out", text: "-> auth/routes.py (modified)" },
      { type: "out", text: "" },
      { type: "cmd", prompt: "~", text: "Confirm? [y/N] y" },
      { type: "success", text: "Workspace resurrected in 94ms" },
    ];

    let li = 0;
    const typeNext = () => {
      if (disposed || li >= lines.length) {
        return;
      }

      const line = lines[li];
      if (line.type === "cmd") {
        const el = document.createElement("div");
        el.className = "t-line";

        const prompt = document.createElement("span");
        prompt.className = "t-prompt";
        prompt.textContent = `${line.prompt ?? "~"} $`;
        el.appendChild(prompt);

        const cmd = document.createElement("span");
        cmd.className = "t-cmd";
        el.appendChild(cmd);
        tb.appendChild(el);

        let c = 0;
        const intervalId = window.setInterval(() => {
          if (disposed) {
            clearInterval(intervalId);
            return;
          }
          c += 1;
          cmd.textContent = line.text.slice(0, c);
          if (c >= line.text.length) {
            clearInterval(intervalId);
            li += 1;
            const timerId = window.setTimeout(typeNext, 400);
            timers.push(timerId);
          }
        }, 30);
        intervals.push(intervalId);
      } else {
        const el = document.createElement("div");
        const cls = {
          out: "t-out",
          highlight: "t-out t-highlight",
          warn: "t-out t-warn",
          success: "t-out t-success",
        }[line.type];
        el.className = cls;
        el.textContent = line.text;
        tb.appendChild(el);
        li += 1;
        const timerId = window.setTimeout(typeNext, 120);
        timers.push(timerId);
      }

      tb.scrollTop = tb.scrollHeight;
    };
    timers.push(window.setTimeout(typeNext, 1800));

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
      "auth/jwt_handler.py": {
        label: "Retriever - Memory Match - auth/jwt_handler.py",
        text: "Branch: feat/auth - 2 hours ago\n\nContext: Implementing JWT authentication with RS256 signing algorithm. 24-hour access token expiry with refresh token rotation. Stored session in PostgreSQL-backed auth database.\n\nRelevant symbols: create_access_token(), verify_token(), refresh_token_endpoint()",
      },
      "agents/retriever.py": {
        label: "Retriever - Memory Match - agents/retriever.py",
        text: "Branch: feat/mcp - 5 hours ago\n\nContext: Cross-workspace semantic search added to Retriever Agent. ChromaDB collections isolated by user_id. Cosine similarity threshold set at 0.72 for high-signal results.\n\nRelevant symbols: search_memory(), upsert_snapshot(), cross_project_search()",
      },
      "security/firewall.ts": {
        label: "Retriever - Memory Match - security/firewall.ts",
        text: "Branch: feat/security - 1 day ago\n\nContext: Semantic Firewall built to detect and redact secrets before any snapshot leaves the local machine. Pattern matching for API keys, JWT tokens, passwords, env vars.\n\nRelevant symbols: FirewallRule, redactSecrets(), scanSnapshot()",
      },
      "agents/simulator.py": {
        label: "Retriever - Memory Match - agents/simulator.py",
        text: "Branch: feat/simulator - 2 days ago\n\nContext: Simulator Agent added as the 4th agent in the pipeline. Runs git status + diff before any resurrection to generate a SafetyReport. Blocks execution if destructive conflicts detected.\n\nRelevant symbols: run_preflight(), generate_safety_report(), check_unstashed_files()",
      },
      "services/vector_db.py": {
        label: "Retriever - Memory Match - services/vector_db.py",
        text: "Branch: main - 3 days ago\n\nContext: VectorDB service abstraction over ChromaDB. Per-user collection management, snapshot upsert with 1536d embeddings, and semantic similarity search with metadata filtering.\n\nRelevant symbols: VectorDBService, upsert_snapshot(), semantic_search(), get_or_create_collection()",
      },
    };

    const queryMap: Record<string, string> = {
      "jwt token flow": "auth/jwt_handler.py",
      "vector search logic": "agents/retriever.py",
      "where are secrets handled": "security/firewall.ts",
      "git branch conflicts": "agents/simulator.py",
      "rate limiting implementation": "services/vector_db.py",
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
      setResult("Retriever - Searching…", `Searching vector store for: "${q}"\n\nRunning semantic retrieval…`);

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
            `Searching vector store for: "${q}"\n\nRunning cosine similarity search across ${Math.floor(Math.random() * 800) + 200} stored snapshots…\n\nTop result: similarity score 0.${Math.floor(Math.random() * 15) + 80} - context match found in active workspace history.`,
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
      disposed = true;
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(canvasRaf);
      timers.forEach((t) => clearTimeout(t));
      intervals.forEach((i) => clearInterval(i));
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
            PM
          </button>
          <a className="nav-login" href="/login">
            Login
          </a>
          <a className="nav-cta" href={extensionMarketplaceUrl} target="_blank" rel="noreferrer">
            Install Extension -&gt;
          </a>
        </div>
      </nav>

      <section className="hero">
        <canvas id="neural-canvas" />

        <div className="hero-content">
          <div className="hero-eyebrow">VS Code Extension - Multi-Agent AI - Vector Memory</div>
          <h1 className="hero-title">
            Your IDE
            <br />
            <em>never</em>
            <br />
            forgets.
          </h1>
          <p className="hero-sub">
            SecondCortex is a persistent AI memory layer for VS Code - it captures your workspace context as you code,
            stores it as searchable vector embeddings, and lets you restore any past session with a natural language
            command.
          </p>
          <div className="hero-actions">
            <a className="btn-primary btn-large" href={extensionMarketplaceUrl} target="_blank" rel="noreferrer">
              Install on VS Code
            </a>
            <button className="btn-secondary btn-large" type="button">
              Read the Docs
            </button>
          </div>
        </div>

        <div className="hero-terminal">
          <div className="terminal-window">
            <div className="terminal-bar">
              <div className="t-dot red" />
              <div className="t-dot yellow" />
              <div className="t-dot green" />
              <span className="terminal-title">cortex - secondcortex-backend</span>
            </div>
            <div className="terminal-body" id="terminal-body" />
          </div>
        </div>
      </section>

      <div className="ticker-wrap">
        <div className="ticker-track" id="ticker-track">
          <span className="ticker-item">Planner Agent</span>
          <span className="ticker-item">Retriever Agent</span>
          <span className="ticker-item">Executor Agent</span>
          <span className="ticker-item">Simulator Sub-Agent</span>
          <span className="ticker-item">ChromaDB Vector Store</span>
          <span className="ticker-item">MCP Server</span>
          <span className="ticker-item">Semantic Firewall</span>
          <span className="ticker-item">Shadow Graph</span>
          <span className="ticker-item">JWT Auth</span>
          <span className="ticker-item">Azure Deployment</span>
          <span className="ticker-item">FastAPI Backend</span>
          <span className="ticker-item">GPT-4o</span>
          <span className="ticker-item">Groq / Llama-3.1</span>
          <span className="ticker-item">Planner Agent</span>
          <span className="ticker-item">Retriever Agent</span>
          <span className="ticker-item">Executor Agent</span>
          <span className="ticker-item">Simulator Sub-Agent</span>
          <span className="ticker-item">ChromaDB Vector Store</span>
          <span className="ticker-item">MCP Server</span>
          <span className="ticker-item">Semantic Firewall</span>
          <span className="ticker-item">Shadow Graph</span>
          <span className="ticker-item">JWT Auth</span>
          <span className="ticker-item">Azure Deployment</span>
          <span className="ticker-item">FastAPI Backend</span>
          <span className="ticker-item">GPT-4o</span>
          <span className="ticker-item">Groq / Llama-3.1</span>
        </div>
      </div>

      <div className="stats-bar reveal">
        <div className="stat-item">
          <div className="stat-num" data-target="3">
            0
          </div>
          <div className="stat-label">Core Agents</div>
        </div>
        <div className="stat-item">
          <div className="stat-num" data-target="1536">
            0
          </div>
          <div className="stat-label">Embedding Dimensions</div>
        </div>
        <div className="stat-item">
          <div className="stat-num" data-target="7">
            0
          </div>
          <div className="stat-label">Technical Pivots Shipped</div>
        </div>
        <div className="stat-item">
          <div className="stat-num" data-target="2" data-suffix="s">
            0s
          </div>
          <div className="stat-label">Typical Retrieval Latency</div>
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
          Jump directly to core workflows from one place. Main workflows stay in the navbar, and secondary links are
          organized in the footer.
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
          IDE events are captured in the background, embedded into a vector store, and made searchable - so any agent
          or external tool can pull relevant context when you need it.
        </p>

        <div className="pipeline reveal">
          <div className="pipeline-track" />
          <div className="pipeline-nodes">
            <div className="pipeline-node">
              <div className="node-index">01</div>
              <div className="node-title">Capture</div>
              <div className="node-desc">
                The VS Code extension monitors every IDE event - open tabs, active files, terminal output, git state,
                with a debounced snapshot system.
              </div>
              <span className="node-tag">eventCapture.ts</span>
            </div>
            <div className="pipeline-node">
              <div className="node-index">02</div>
              <div className="node-title">Embed</div>
              <div className="node-desc">
                Snapshots are vectorized using text-embedding-3-small into 1536-dimensional space and stored in a
                persistent ChromaDB instance per user.
              </div>
              <span className="node-tag">vector_db.py</span>
            </div>
            <div className="pipeline-node">
              <div className="node-index">03</div>
              <div className="node-title">Retrieve</div>
              <div className="node-desc">
                When you trigger a session restore or ask a question, the Retriever searches your vector store by
                semantic similarity - returning the most relevant snapshots, including those from other repos.
              </div>
              <span className="node-tag">retriever.py</span>
            </div>
            <div className="pipeline-node">
              <div className="node-index">04</div>
              <div className="node-title">Execute</div>
              <div className="node-desc">
                After you confirm the Planner&apos;s proposed actions, the Executor applies them to your workspace - opening
                files, switching branches, running the Simulator sub-agent to check for git conflicts first.
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
          Three agents.
          <br />
          <em>One pipeline.</em>
        </div>
        <p className="section-desc reveal">
          A focused multi-agent architecture where each component has a distinct role. The Executor runs a built-in
          Simulator sub-agent for pre-flight checks before touching your workspace.
        </p>

        <div className="agents-grid reveal agents-grid-three">
          <div className="agent-card">
            <div className="agent-icon">
              <div className="agent-icon-inner agent-code">PLN</div>
            </div>
            <div className="agent-name">Planner</div>
            <div className="agent-role">Task Decomposition</div>
            <div className="agent-desc">
              Takes a natural language request and breaks it into a structured, step-by-step action plan. Uses
              retrieved context from your memory to make decisions relevant to your actual codebase - not guesses.
            </div>
            <div className="agent-spec">
              <div className="spec-item">LLM: GPT-4o via GitHub Models</div>
              <div className="spec-item">Output: Structured action plan</div>
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
              Searches your ChromaDB vector store using cosine similarity to surface relevant past context - open
              files, git branches, code summaries. Also exposed as an MCP endpoint so Claude and Cursor can query it
              directly.
            </div>
            <div className="agent-spec">
              <div className="spec-item">Store: ChromaDB (per-user namespace)</div>
              <div className="spec-item">Embeddings: text-embedding-3-small</div>
              <div className="spec-item">Exposed via MCP SSE endpoint</div>
            </div>
          </div>
          <div className="agent-card">
            <div className="agent-icon">
              <div className="agent-icon-inner agent-code">EXC</div>
            </div>
            <div className="agent-name">Executor</div>
            <div className="agent-role">Workspace Restoration</div>
            <div className="agent-desc">
              Applies the approved action plan to your VS Code workspace - opening files, switching branches,
              restoring terminal context. Runs the Simulator sub-agent first to check for unstashed changes or branch
              conflicts before making any changes.
            </div>
            <div className="agent-spec">
              <div className="spec-item">LLM: Groq Llama-3.1 (fast inference)</div>
              <div className="spec-item">Sub-agent: Simulator (git pre-flight)</div>
              <div className="spec-item">PowerShell + bash compatible</div>
            </div>
          </div>
        </div>
      </section>

      <section id="memory" className="memory-demo">
        <div className="section-label">Live Memory</div>
        <div className="section-title">
          Query your
          <br />
          <em>past work.</em>
        </div>

        <div className="demo-split reveal">
          <div className="memory-visualizer">
            <div className="memory-header">
              <span>ChromaDB - User Namespace</span>
              <span className="mem-status">LIVE</span>
            </div>
            <div className="memory-entries" id="mem-entries">
              <div
                className="mem-entry active"
                data-file="auth/jwt_handler.py"
                data-branch="feat/auth"
                data-time="2h ago"
              >
                <div className="mem-file">auth/jwt_handler.py</div>
                <div className="mem-summary">Implemented RS256 JWT signing with 24h expiry and refresh token rotation.</div>
                <div className="mem-meta">
                  <span>feat/auth</span>
                  <span>2h ago</span>
                </div>
              </div>
              <div
                className="mem-entry"
                data-file="agents/retriever.py"
                data-branch="feat/mcp"
                data-time="5h ago"
              >
                <div className="mem-file">agents/retriever.py</div>
                <div className="mem-summary">
                  Added cross-workspace semantic search with ChromaDB collection isolation per user_id.
                </div>
                <div className="mem-meta">
                  <span>feat/mcp</span>
                  <span>5h ago</span>
                </div>
              </div>
              <div
                className="mem-entry"
                data-file="security/firewall.ts"
                data-branch="feat/security"
                data-time="1d ago"
              >
                <div className="mem-file">security/firewall.ts</div>
                <div className="mem-summary">Semantic Firewall redacts API keys and secrets locally before upload.</div>
                <div className="mem-meta">
                  <span>feat/security</span>
                  <span>1d ago</span>
                </div>
              </div>
              <div
                className="mem-entry"
                data-file="agents/simulator.py"
                data-branch="feat/simulator"
                data-time="2d ago"
              >
                <div className="mem-file">agents/simulator.py</div>
                <div className="mem-summary">Pre-flight simulator generates conflict Safety Reports from git diff.</div>
                <div className="mem-meta">
                  <span>feat/simulator</span>
                  <span>2d ago</span>
                </div>
              </div>
              <div className="mem-entry" data-file="services/vector_db.py" data-branch="main" data-time="3d ago">
                <div className="mem-file">services/vector_db.py</div>
                <div className="mem-summary">VectorDB service wrapping ChromaDB with upsert and semantic search.</div>
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
              Natural language semantic search across your entire development history - not just grep, but meaning.
            </div>

            <div className="query-input-wrap">
              <input
                className="query-input"
                id="query-input"
                type="text"
                placeholder="How does authentication work in this project?"
              />
              <button className={`query-btn ${queryLoading ? "is-loading" : ""}`} id="query-btn" type="button" disabled={queryLoading}>
                {queryLoading ? (
                  <>
                    <span className="loading-ring" aria-hidden="true" />
                    Searching…
                  </>
                ) : (
                  "SEARCH"
                )}
              </button>
            </div>

            <div>
              <div className="query-try">Try asking:</div>
              <div className="query-suggestions">
                <div className="suggestion-chip" data-query="JWT token flow">
                  JWT token flow
                </div>
                <div className="suggestion-chip" data-query="vector search logic">
                  vector search logic
                </div>
                <div className="suggestion-chip" data-query="where are secrets handled">
                  where are secrets handled
                </div>
                <div className="suggestion-chip" data-query="git branch conflicts">
                  git branch conflicts
                </div>
                <div className="suggestion-chip" data-query="rate limiting implementation">
                  rate limiting implementation
                </div>
              </div>
            </div>

            <div className="query-result" id="query-result" aria-live="polite">
              <div className="result-label">Retriever - Awaiting Query</div>
              <div className="result-text" id="result-text">
                Click any memory entry or type a query to see semantic retrieval in action.
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
          Credentials never leave your machine unredacted. User data is namespace-isolated, and no workspace change
          runs without your explicit approval.
        </p>

        <div className="security-grid reveal">
          <div className="security-card">
            <div className="security-icon">
              <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
                <rect x="1" y="1" width="26" height="26" stroke="rgba(255,255,255,0.25)" strokeWidth="1" />
                <path d="M7 14h14M14 7v14" stroke="rgba(255,255,255,0.6)" strokeWidth="1.5" />
                <circle cx="14" cy="14" r="4" stroke="rgba(255,255,255,0.35)" strokeWidth="1" />
              </svg>
            </div>
            <div className="security-title">Semantic Firewall</div>
            <div className="security-text">
              Redacts API keys, tokens, and credentials from every snapshot before it leaves your machine.
              Pattern-matched against common secret formats - env vars, bearer tokens, private keys.
            </div>
          </div>
          <div className="security-card">
            <div className="security-icon">
              <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
                <rect x="1" y="1" width="26" height="26" stroke="rgba(255,255,255,0.25)" strokeWidth="1" />
                <rect x="7" y="7" width="6" height="6" stroke="rgba(255,255,255,0.6)" strokeWidth="1" />
                <rect x="15" y="7" width="6" height="6" stroke="rgba(255,255,255,0.25)" strokeWidth="1" />
                <rect x="7" y="15" width="6" height="6" stroke="rgba(255,255,255,0.25)" strokeWidth="1" />
                <rect x="15" y="15" width="6" height="6" stroke="rgba(255,255,255,0.25)" strokeWidth="1" />
              </svg>
            </div>
            <div className="security-title">Per-User Isolation</div>
            <div className="security-text">
              Each user gets a separate ChromaDB collection namespace. JWT-authenticated API endpoints ensure no
              cross-user data leakage at the storage or query layer.
            </div>
          </div>
          <div className="security-card">
            <div className="security-icon">
              <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
                <rect x="1" y="1" width="26" height="26" stroke="rgba(255,255,255,0.25)" strokeWidth="1" />
                <polyline points="7,14 12,19 21,9" stroke="rgba(255,255,255,0.7)" strokeWidth="1.5" fill="none" />
              </svg>
            </div>
            <div className="security-title">Confirmation Before Execution</div>
            <div className="security-text">
              The Executor never runs without your sign-off. Every action plan is displayed as a readable summary in
              the VS Code sidebar before any workspace change is made.
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
            <div className="arch-box highlight">VS Code Extension (TypeScript)</div>
            <div className="arch-arrow">-&gt;</div>
            <div className="arch-box">Event Capture + Debouncer</div>
            <div className="arch-arrow">-&gt;</div>
            <div className="arch-box">Semantic Firewall</div>
            <div className="arch-arrow">-&gt;</div>
            <div className="arch-box primary">FastAPI Backend</div>
            <div className="arch-label">Data Ingestion Layer</div>
          </div>

          <div className="arch-sep" />

          <div className="arch-row">
            <div className="arch-box primary">FastAPI Backend</div>
            <div className="arch-arrow">-&gt;</div>
            <div className="arch-box">LLM Client (GPT-4o / Groq)</div>
            <div className="arch-arrow">-&gt;</div>
            <div className="arch-box">3-Agent Pipeline</div>
            <div className="arch-arrow">-&gt;</div>
            <div className="arch-box highlight">ChromaDB (1536d vectors)</div>
            <div className="arch-label">Intelligence Layer</div>
          </div>

          <div className="arch-sep" />

          <div className="arch-row">
            <div className="arch-box">MCP SSE Server</div>
            <div className="arch-arrow">-&gt;</div>
            <div className="arch-box highlight">Claude / Cursor / Any AI</div>
            <div className="arch-note">
              - External AI tools can query your Cortex memory natively via Model Context Protocol
            </div>
            <div className="arch-label">Integration Layer</div>
          </div>

          <div className="arch-sep" />

          <div className="arch-row">
            <div className="arch-box">Azure Web App (Backend)</div>
            <div className="arch-arrow">+</div>
            <div className="arch-box">GitHub Actions CI/CD</div>
            <div className="arch-arrow">+</div>
            <div className="arch-box">Docker (GHCR)</div>
            <div className="arch-arrow">+</div>
            <div className="arch-box highlight">Next.js Web Dashboard</div>
            <div className="arch-label">Deployment Layer</div>
          </div>
        </div>
      </section>

      <section className="cta-section">
        <div className="cta-glow" />
        <p className="section-label cta-label">Early Access</p>
        <h2 className="cta-title">
          Build with
          <br />
          <em>context.</em>
        </h2>
        <p className="cta-sub">Install the VS Code extension. SecondCortex starts building your memory immediately.</p>
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
            <a href="#memory">Memory Demo</a>
            <a href="#security">Security</a>
          </div>
        </div>

        <div className="footer-links-group">
          <div className="footer-links-title">Access</div>
          <div className="footer-links">
            <a href="/login">Login</a>
            <a href="/signup">Sign Up</a>
            <a href="/live">Live Graph</a>
            <a href="/live?pm=true">PM Dashboard</a>
            <a href="/testing">Testing</a>
          </div>
        </div>

        <div className="footer-links-group">
          <div className="footer-links-title">Resources</div>
          <div className="footer-links">
            <a href={githubRepoUrl} target="_blank" rel="noreferrer">GitHub</a>
            <a href={extensionMarketplaceUrl} target="_blank" rel="noreferrer">VS Code Marketplace</a>
            <a href="#arch">Architecture</a>
          </div>
        </div>

        <div>Copyright 2026 SecondCortex Labs</div>
      </footer>

      {showPmModal && (
        <div className="sc-modal-wrap">
          <div className="sc-modal-backdrop" onClick={() => setShowPmModal(false)} />
          <div className="sc-modal-card pm-login-card">
            <div className="sc-auth-header">
              <p className="sc-auth-eyebrow">Project Manager Access</p>
              <h2 className="sc-auth-title">PM Login</h2>
              <p className="sc-auth-sub">Log in as PM or continue with guest access to review team progress.</p>
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
                  "Login as PM"
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
                  "Guest Login"
                )}
              </button>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
