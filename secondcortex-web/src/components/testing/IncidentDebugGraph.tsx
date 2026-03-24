type IncidentHypothesis = {
  id: string;
  rank: number;
  cause: string;
  confidence: number;
  supportingEvidenceIds: string[];
};

type IncidentRecoveryOption = {
  strategy: string;
  risk: string;
  blastRadius: string;
  estimatedTimeMinutes: number;
  commands: string[];
};

type IncidentEvidenceNode = {
  id: string;
  type: string;
  timestamp: string;
  file: string;
  branch: string;
  summary: string;
  source: string;
};

export type IncidentPacket = {
  incidentId: string;
  summary: string;
  confidence: number;
  hypotheses: IncidentHypothesis[];
  recoveryOptions: IncidentRecoveryOption[];
  contradictions: string[];
  evidenceNodes: IncidentEvidenceNode[];
  disproofChecks: string[];
};

export default function IncidentDebugGraph({ packet }: { packet: IncidentPacket }) {
  return (
    <section className="sc-dashboard-panel">
      <div className="sc-dashboard-panel-inner" style={{ flexDirection: "column", alignItems: "stretch", gap: 12 }}>
        <div>
          <h2 className="sc-dashboard-h2">4. Incident Debug Graph + Recovery Simulator</h2>
          <p className="sc-dashboard-p">
            Incident: {packet.incidentId} • Confidence: {(packet.confidence * 100).toFixed(0)}%
          </p>
          <p className="sc-auth-sub">{packet.summary}</p>
        </div>

        <div className="sc-guide-grid" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))" }}>
          <div className="sc-guide-card" style={{ display: "grid", gap: 8 }}>
            <h3 className="sc-guide-title">Evidence Nodes</h3>
            {packet.evidenceNodes.length > 0 ? (
              packet.evidenceNodes.map((node) => (
                <div key={node.id} className="sc-auth-sub">
                  <strong>{node.id}</strong> • {node.type}<br />
                  {node.file} @ {node.branch}<br />
                  {node.timestamp}<br />
                  {node.source}
                </div>
              ))
            ) : (
              <p className="sc-auth-sub">No evidence nodes returned.</p>
            )}
          </div>

          <div className="sc-guide-card" style={{ display: "grid", gap: 8 }}>
            <h3 className="sc-guide-title">Hypotheses</h3>
            {packet.hypotheses.length > 0 ? (
              packet.hypotheses.map((hypothesis) => (
                <div key={hypothesis.id} className="sc-auth-sub">
                  <strong>#{hypothesis.rank}</strong> {hypothesis.cause} ({(hypothesis.confidence * 100).toFixed(0)}%)<br />
                  Evidence: {hypothesis.supportingEvidenceIds.join(", ") || "none"}
                </div>
              ))
            ) : (
              <p className="sc-auth-sub">No ranked hypotheses returned.</p>
            )}
          </div>

          <div className="sc-guide-card" style={{ display: "grid", gap: 8 }}>
            <h3 className="sc-guide-title">Recovery Options</h3>
            {packet.recoveryOptions.length > 0 ? (
              packet.recoveryOptions.map((option) => (
                <div key={option.strategy} className="sc-auth-sub">
                  <strong>{option.strategy}</strong> • risk {option.risk}<br />
                  Blast radius: {option.blastRadius} • ETA: {option.estimatedTimeMinutes} min
                  <pre className="sc-guide-code" style={{ whiteSpace: "pre-wrap", marginTop: 8 }}>
                    {option.commands.join("\n") || "No command preview."}
                  </pre>
                </div>
              ))
            ) : (
              <p className="sc-auth-sub">No recovery options returned.</p>
            )}
          </div>
        </div>

        <div className="sc-guide-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <div className="sc-guide-card" style={{ display: "grid", gap: 8 }}>
            <h3 className="sc-guide-title">Contradictions</h3>
            {packet.contradictions.length > 0 ? (
              <ul className="sc-auth-sub">
                {packet.contradictions.map((item, index) => (
                  <li key={`${item}-${index}`}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="sc-auth-sub">No contradictions detected.</p>
            )}
          </div>
          <div className="sc-guide-card" style={{ display: "grid", gap: 8 }}>
            <h3 className="sc-guide-title">Disproof Checks</h3>
            {packet.disproofChecks.length > 0 ? (
              <ul className="sc-auth-sub">
                {packet.disproofChecks.map((item, index) => (
                  <li key={`${item}-${index}`}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="sc-auth-sub">No disproof checks generated.</p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
