export const metadata = {
  title: 'SecondCortex - Offline Setup',
  description: 'Offline deterministic setup options for local SecondCortex demos.',
};

export default function OfflineSetupPage() {
  return (
    <main className="sc-dashboard-wrap offline-setup-page" style={{ paddingTop: '84px' }}>
      <div className="sc-dashboard-inner offline-setup-inner">
        <div className="sc-section-header offline-setup-header">
          <p className="section-label">Offline Setup</p>
          <h1 className="section-title">Run Fully Local</h1>
          <p className="section-desc">
            Choose a deterministic local stack for demos. Both options keep data local with no required cloud dependency.
          </p>
        </div>

        <div className="sc-dashboard-panel">
          <div className="sc-dashboard-panel-inner offline-panel-inner">
            <h2 className="sc-dashboard-h2">Option 1: Local DB + Azure OpenAI</h2>
            <p className="sc-dashboard-p">Use a local ChromaDB vector database with Azure OpenAI for model inference.</p>
            <pre className="query-result offline-code" style={{ whiteSpace: 'pre-wrap' }}>{`# Python backend
pip install -r requirements.txt

# Start local ChromaDB and other services
docker compose up -d

# Run backend
uvicorn secondcortex-backend.main:app --reload --port 8000`}</pre>
            <div className="offline-box">
              <h3 className="offline-subtitle">Installation Instructions</h3>
              <p className="sc-dashboard-p"><strong>ChromaDB Setup:</strong> ChromaDB runs automatically via Docker Compose. Verify it is running at <a href="http://localhost:8000" target="_blank" rel="noreferrer">http://localhost:8000</a></p>
            </div>
            <div className="offline-box">
              <h3 className="offline-subtitle">Links</h3>
              <div className="offline-link-list">
                <a href="https://learn.microsoft.com/azure/ai-services/openai/" target="_blank" rel="noreferrer">Azure OpenAI Documentation</a>
                <a href="https://docs.trychroma.com/" target="_blank" rel="noreferrer">ChromaDB Documentation</a>
                <a href="https://github.com/chroma-core/chroma" target="_blank" rel="noreferrer">ChromaDB GitHub</a>
              </div>
            </div>
          </div>
        </div>

        <div className="sc-dashboard-panel">
          <div className="sc-dashboard-panel-inner offline-panel-inner">
            <h2 className="sc-dashboard-h2">Option 2: Fully Local (ChromaDB + Ollama)</h2>
            <p className="sc-dashboard-p">Run both storage and model inference locally for a fully offline demo path with zero cloud dependencies.</p>
            <pre className="query-result offline-code" style={{ whiteSpace: 'pre-wrap' }}>{`# Step 1: Install Ollama locally
ollama pull llama3.1

# Step 2: Start Ollama server (runs on http://localhost:11434)
ollama serve

# Step 3: In a new terminal, start local services
docker compose up -d

# Step 4: Run backend with local model provider env variable
# Windows (PowerShell)
$env:SECOND_CORTEX_MODEL_PROVIDER = 'ollama'
uvicorn secondcortex-backend.main:app --reload --port 8000

# macOS/Linux
export SECOND_CORTEX_MODEL_PROVIDER=ollama
uvicorn secondcortex-backend.main:app --reload --port 8000`}</pre>
            <div className="offline-box">
              <h3 className="offline-subtitle">Installation Instructions</h3>
              <div className="sc-dashboard-p">
                <p><strong>Ollama Setup:</strong></p>
                <ol className="offline-steps">
                  <li>Download and install Ollama from <a href="https://ollama.com" target="_blank" rel="noreferrer">ollama.com</a></li>
                  <li>Run <code>ollama pull llama3.1</code> to download the model (first time only)</li>
                  <li>Start the server with <code>ollama serve</code></li>
                  <li>Verify it is running at <a href="http://localhost:11434" target="_blank" rel="noreferrer">http://localhost:11434</a></li>
                </ol>
                <p><strong>ChromaDB Setup:</strong> ChromaDB runs automatically via Docker Compose. Verify it is running at <a href="http://localhost:8000" target="_blank" rel="noreferrer">http://localhost:8000</a></p>
              </div>
            </div>

            <div className="offline-box">
              <h3 className="offline-subtitle">Links</h3>
              <div className="offline-link-list">
                <a href="https://ollama.com/" target="_blank" rel="noreferrer">Ollama Official Website</a>
                <a href="https://github.com/ollama/ollama" target="_blank" rel="noreferrer">Ollama GitHub Repository</a>
                <a href="https://docs.trychroma.com/" target="_blank" rel="noreferrer">ChromaDB Documentation</a>
                <a href="https://github.com/chroma-core/chroma" target="_blank" rel="noreferrer">ChromaDB GitHub</a>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
