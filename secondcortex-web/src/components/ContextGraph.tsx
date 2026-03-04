'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
    ReactFlow,
    Background,
    Controls,
    MiniMap,
    useNodesState,
    useEdgesState,
    addEdge,
    type Node,
    type Edge,
    type Connection,
    MarkerType,
    BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import * as d3 from 'd3-force';

// ── Types ─────────────────────────────────────────────────────

interface SnapshotEvent {
    id: string;
    timestamp: string;
    active_file: string;
    git_branch: string | null;
    summary: string;
    entities: string[];
    relations: Array<{ source: string; target: string; relation: string }>;
}

// ── Node styling ──────────────────────────────────────────────

const NODE_STYLES: Record<string, React.CSSProperties> = {
    commit: {
        background: '#667eea',
        color: '#fff',
        border: '1px solid rgba(255,255,255,0.2)',
        borderRadius: '12px',
        padding: '12px 18px',
        fontSize: '13px',
        fontWeight: 600,
        textWrap: 'balance',
    },
    file: {
        background: '#f5576c',
        color: '#fff',
        border: '1px solid rgba(255,255,255,0.2)',
        borderRadius: '10px',
        padding: '12px 16px',
        fontSize: '13px',
        fontWeight: 600,
        textWrap: 'balance',
    },
    entity: {
        background: '#0f172a',
        color: '#38bdf8',
        border: '1px solid rgba(56, 189, 248, 0.4)',
        borderRadius: '8px',
        padding: '8px 14px',
        fontSize: '12px',
        fontWeight: 500,
        textWrap: 'balance',
    },
    reasoning: {
        background: '#10b981',
        color: '#ecfdf5',
        border: '1px solid rgba(255,255,255,0.3)',
        borderRadius: '16px',
        padding: '16px 20px',
        fontSize: '14px',
        fontWeight: 600,
        textWrap: 'balance',
        maxWidth: 280,
    },
};

// ── Main Component ──────────────────────────────────────────────

interface ContextGraphProps {
    backendUrl?: string;
    pollIntervalMs?: number;
    apiKey?: string;
}

export default function ContextGraph({
    backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'https://sc-backend-suhaan.azurewebsites.net',
    pollIntervalMs = 3000,
    apiKey = process.env.NEXT_PUBLIC_API_KEY || '',
}: ContextGraphProps) {
    const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
    const [isConnected, setIsConnected] = useState(false);
    const [lastEvent, setLastEvent] = useState<string>('Waiting for events…');
    const seenEventsRef = useRef(new Set<string>());

    // D3 Force Simulation logic
    const simulationRef = useRef<d3.Simulation<any, any> | null>(null);

    const onConnect = useCallback(
        (connection: Connection) => setEdges((eds) => addEdge(connection, eds)),
        [setEdges]
    );

    // Run force simulation whenever nodes or edges update structurally
    useEffect(() => {
        if (nodes.length === 0) return;

        // Start Force Simulation from Center
        const simNodes = nodes.map((n) => ({ ...n, x: n.position.x, y: n.position.y }));

        // Ensure edges only reference existing nodes (prevents D3 "node not found" crashes during async renders)
        const nodeIds = new Set(simNodes.map(n => n.id));
        const simLinks = edges
            .filter(e => nodeIds.has(e.source) && nodeIds.has(e.target))
            .map((e) => ({ source: e.source, target: e.target, id: e.id }));

        const simulation = d3.forceSimulation(simNodes)
            // Gentler outward repulsion so nodes don't violently explode
            .force('charge', d3.forceManyBody().strength(-400).distanceMax(800))
            // Softer, longer links so the graph breathes
            .force('link', d3.forceLink(simLinks).id((d: any) => d.id).distance(160).strength(0.4))
            // Very soft gravity to center
            .force('center', d3.forceCenter(0, 0).strength(0.02))
            // Stricter collision so they don't overlap and vibrate
            .force('collide', d3.forceCollide().radius((d: any) => {
                const label = d.data?.label || '';
                return Math.max(90, label.length * 6);
            }).iterations(4))
            // Lower initial heat and fast decay makes it drift beautifully into place then freeze
            .alpha(0.3)
            .alphaDecay(0.04)
            .restart();

        simulation.on('tick', () => {
            // Update React Flow nodes on every physics tick for beautiful animation
            setNodes((currentNodes) =>
                currentNodes.map((n) => {
                    const simNode = simNodes.find((sn) => sn.id === n.id);
                    if (simNode) {
                        return {
                            ...n,
                            position: { x: simNode.x ?? 0, y: simNode.y ?? 0 },
                        };
                    }
                    return n;
                })
            );
        });

        simulationRef.current = simulation;

        return () => {
            simulation.stop();
        };
        // We explicitly do NOT want to re-run this effect on every tick, only when arrays change length.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [nodes.length, edges.length]);

    // ── Process new events incrementally ────────────────────────

    const processEvents = useCallback(
        (events: SnapshotEvent[]) => {
            let hasNew = false;

            setNodes((currentNodes) => {
                const updatedNodes = [...currentNodes];
                const newEdgesLocal: Edge[] = [];
                const nodeMap = new Map<string, Node>(updatedNodes.map(n => [n.id, n]));

                events.forEach((event) => {
                    if (seenEventsRef.current.has(event.id)) return;
                    seenEventsRef.current.add(event.id);
                    hasNew = true;

                    // 1. File Node (Deduplicated)
                    const activeFile = event.active_file || 'unknown';
                    const fileName = activeFile.split(/[/\\]/).pop() ?? activeFile;
                    const fileNodeId = `file-${fileName}`;
                    if (!nodeMap.has(fileNodeId)) {
                        const fileNode: Node = {
                            id: fileNodeId,
                            data: { label: `📁 ${fileName}` },
                            // Spawn new nodes near center (0,0) to grow outwards
                            position: { x: (Math.random() - 0.5) * 50, y: (Math.random() - 0.5) * 50 },
                            style: NODE_STYLES.file,
                        };
                        nodeMap.set(fileNodeId, fileNode);
                        updatedNodes.push(fileNode);
                    }

                    // 2. Branch Node (Deduplicated)
                    if (event.git_branch) {
                        const branchNodeId = `branch-${event.git_branch}`;
                        if (!nodeMap.has(branchNodeId)) {
                            const branchNode: Node = {
                                id: branchNodeId,
                                data: { label: `🌿 ${event.git_branch}` },
                                position: { x: (Math.random() - 0.5) * 50, y: (Math.random() - 0.5) * 50 },
                                style: NODE_STYLES.commit,
                            };
                            nodeMap.set(branchNodeId, branchNode);
                            updatedNodes.push(branchNode);
                        }

                        newEdgesLocal.push({
                            id: `e-${branchNodeId}-${fileNodeId}-${event.id}`, // Add event ID so edges aren't exactly duplicates if redrawn
                            source: branchNodeId,
                            target: fileNodeId,
                            animated: true,
                            style: { stroke: 'rgba(102, 126, 234, 0.8)', strokeWidth: 2 },
                        });
                    }

                    // 3. Entity Nodes (Deduplicated)
                    event.entities?.forEach((entity) => {
                        const entityNodeId = `entity-${entity}`;
                        if (!nodeMap.has(entityNodeId)) {
                            const entityNode: Node = {
                                id: entityNodeId,
                                data: { label: `⚡ ${entity}` },
                                position: { x: (Math.random() - 0.5) * 50, y: (Math.random() - 0.5) * 50 },
                                style: NODE_STYLES.entity,
                            };
                            nodeMap.set(entityNodeId, entityNode);
                            updatedNodes.push(entityNode);
                        }

                        newEdgesLocal.push({
                            id: `e-${fileNodeId}-${entityNodeId}`,
                            source: fileNodeId,
                            target: entityNodeId,
                            style: { stroke: 'rgba(56, 189, 248, 0.5)', strokeDasharray: '4,6', strokeWidth: 1.5 },
                        });
                    });

                    // 4. Reasoning/Event Node (Unique per event)
                    if (event.summary) {
                        const reasoningNodeId = `reason-${event.id}`;
                        const reasoningNode: Node = {
                            id: reasoningNodeId,
                            data: { label: `🧠 ${event.summary}` },
                            position: { x: (Math.random() - 0.5) * 50, y: (Math.random() - 0.5) * 50 },
                            style: NODE_STYLES.reasoning,
                        };
                        nodeMap.set(reasoningNodeId, reasoningNode);
                        updatedNodes.push(reasoningNode);

                        newEdgesLocal.push({
                            id: `e-${reasoningNodeId}-${fileNodeId}`,
                            source: fileNodeId,
                            target: reasoningNodeId,
                            animated: true,
                            style: { stroke: '#10b981', strokeWidth: 2.5 },
                        });
                    }

                    setLastEvent(`${new Date().toLocaleTimeString()} — ${event.summary || (event.active_file ? (event.active_file.split(/[/\\]/).pop()) : 'Activity')}`);
                });

                if (hasNew) {
                    setEdges((currentEdges) => {
                        const edgeMap = new Map<string, Edge>(currentEdges.map(e => [e.id, e]));
                        newEdgesLocal.forEach(e => edgeMap.set(e.id, e));
                        return Array.from(edgeMap.values());
                    });
                }

                return updatedNodes;
            });
        },
        [setNodes, setEdges]
    );

    // ── Poll the backend ────────────────────────────────────────

    useEffect(() => {
        let active = true;

        const poll = async () => {
            try {
                const headers: Record<string, string> = {};
                if (apiKey) {
                    headers['X-API-Key'] = apiKey;
                }
                const res = await fetch(`${backendUrl}/api/v1/events`, { headers });
                if (res.ok) {
                    setIsConnected(true);
                    const data = await res.json();
                    if (Array.isArray(data.events)) {
                        processEvents(data.events);
                    }
                } else {
                    setIsConnected(false);
                }
            } catch {
                setIsConnected(false);
            }
        };

        const interval = setInterval(() => {
            if (active) poll();
        }, pollIntervalMs);

        poll(); // initial

        return () => {
            active = false;
            clearInterval(interval);
        };
    }, [backendUrl, pollIntervalMs, processEvents, apiKey]);

    return (
        <div style={{ width: '100%', height: '100vh', background: '#020617' }}>
            {/* Status bar */}
            <div
                style={{
                    position: 'absolute',
                    top: 24,
                    left: 24,
                    zIndex: 10,
                    display: 'flex',
                    gap: 16,
                    alignItems: 'center',
                }}
            >
                <div
                    style={{
                        background: 'rgba(15, 23, 42, 0.95)',
                        border: '1px solid rgba(255,255,255,0.08)',
                        borderRadius: 16,
                        padding: '12px 20px',
                        color: '#f8fafc',
                        fontSize: 14,
                        fontWeight: 500,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 10,
                    }}
                >
                    <span
                        style={{
                            width: 10,
                            height: 10,
                            borderRadius: '50%',
                            background: isConnected ? '#10b981' : '#ef4444',
                        }}
                    />
                    {isConnected ? 'Syncing Context' : 'Offline'}
                </div>
                <div
                    style={{
                        background: 'rgba(15, 23, 42, 0.95)',
                        border: '1px solid rgba(255,255,255,0.08)',
                        borderRadius: 16,
                        padding: '12px 24px',
                        color: '#cbd5e1',
                        fontSize: 14,
                        maxWidth: 500,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                    }}
                >
                    {lastEvent}
                </div>
            </div>

            {/* Title */}
            <div
                style={{
                    position: 'absolute',
                    top: 24,
                    right: 24,
                    zIndex: 10,
                    background: 'rgba(15, 23, 42, 0.95)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    borderRadius: 16,
                    padding: '16px 24px',
                    color: '#fff',
                    fontSize: 20,
                    fontWeight: 700,
                    letterSpacing: '-0.02em',
                }}
            >
                🧠 SecondCortex <span style={{ opacity: 0.3, fontWeight: 400 }}>| Live Graph</span>
            </div>

            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                fitView
                fitViewOptions={{ padding: 0.2 }}
                minZoom={0.05}
                maxZoom={2}
                style={{ background: '#020617' }} // Slate 950 base
            >
                <Background color="#1e293b" gap={24} size={1} variant={BackgroundVariant.Dots} />
                <Controls
                    style={{
                        background: 'rgba(15, 23, 42, 0.6)',
                        backdropFilter: 'blur(12px)',
                        border: '1px solid rgba(255,255,255,0.1)',
                        borderRadius: 12,
                        padding: 4,
                        boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
                    }}
                />
                <MiniMap
                    nodeColor={(node) => {
                        if (node.id.startsWith('reason')) return '#10b981';
                        if (node.id.startsWith('file')) return '#f5576c';
                        if (node.id.startsWith('branch')) return '#667eea';
                        return '#4facfe';
                    }}
                    maskColor="rgba(2, 6, 23, 0.85)"
                    style={{
                        background: 'rgba(15, 23, 42, 0.6)',
                        backdropFilter: 'blur(12px)',
                        border: '1px solid rgba(255,255,255,0.1)',
                        borderRadius: 16,
                        boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
                    }}
                />
            </ReactFlow>

            {/* Global Styles aligned with web-design-guidelines */}
            <style>{`
                :root {
                    color-scheme: dark;
                }
                @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
                
                body {
                    margin: 0;
                    padding: 0;
                    background: #020617;
                    color: #f8fafc;
                    overflow: hidden;
                    font-family: 'Inter', system-ui, -apple-system, sans-serif;
                }
                
                .react-flow__controls-button {
                    background: transparent !important;
                    border-bottom: 1px solid rgba(255,255,255,0.1) !important;
                    fill: #f8fafc !important;
                    transition: background 0.2s ease;
                }
                .react-flow__controls-button:hover {
                    background: rgba(255,255,255,0.1) !important;
                }
                .react-flow__controls-button:last-child {
                    border-bottom: none !important;
                }
            `}</style>
        </div>
    );
}
