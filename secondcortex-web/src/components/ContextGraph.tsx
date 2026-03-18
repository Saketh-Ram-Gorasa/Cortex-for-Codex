'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    ReactFlow,
    Background,
    MiniMap,
    useNodesState,
    useEdgesState,
    addEdge,
    type Node,
    type Edge,
    type Connection,
    MarkerType,
    BackgroundVariant,
    type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

type VsCodeApi = {
    postMessage: (message: unknown) => void;
};

declare global {
    interface Window {
        acquireVsCodeApi?: () => VsCodeApi;
    }
}

interface SnapshotEvent {
    id: string;
    timestamp: number;
    developer_name: string;
    active_file: string;
    git_branch: string | null;
    summary: string;
}

const NODE_STYLES: Record<string, React.CSSProperties> = {
    commit: {
        background: '#111111',
        color: '#f0f0f0',
        border: '1px solid rgba(255,255,255,0.2)',
        borderRadius: '12px',
        padding: '12px 18px',
        fontSize: '13px',
        fontWeight: 600,
        textWrap: 'balance',
    },
    file: {
        background: '#1a1a1a',
        color: '#f0f0f0',
        border: '1px solid rgba(255,255,255,0.2)',
        borderRadius: '10px',
        padding: '12px 16px',
        fontSize: '13px',
        fontWeight: 600,
        textWrap: 'balance',
    },
    entity: {
        background: '#080808',
        color: 'rgba(255,255,255,0.75)',
        border: '1px solid rgba(255,255,255,0.22)',
        borderRadius: '8px',
        padding: '8px 14px',
        fontSize: '12px',
        fontWeight: 500,
        textWrap: 'balance',
    },
    reasoning: {
        background: '#f0f0f0',
        color: '#080808',
        border: '1px solid rgba(255,255,255,0.55)',
        borderRadius: '16px',
        padding: '16px 20px',
        fontSize: '14px',
        fontWeight: 600,
        textWrap: 'balance',
        maxWidth: 280,
    },
};

interface ContextGraphProps {
    backendUrl?: string;
    token?: string;
    onUnauthorized?: () => void;
}

export default function ContextGraph({
    backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'https://sc-backend-suhaan.azurewebsites.net',
    token = '',
    onUnauthorized,
}: ContextGraphProps) {
    const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
    const [isConnected, setIsConnected] = useState(false);
    const [timeline, setTimeline] = useState<SnapshotEvent[]>([]);
    const [selectedIndex, setSelectedIndex] = useState<number>(0);
    const [isPinnedInPast, setIsPinnedInPast] = useState(false);
    const [lastEvent, setLastEvent] = useState<string>('Waiting for snapshots...');
    const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance<Node, Edge> | null>(null);
    const vscodeApiRef = useRef<VsCodeApi | null>(null);

    const onConnect = useCallback(
        (connection: Connection) => setEdges((eds) => addEdge(connection, eds)),
        [setEdges]
    );

    const selectedSnapshot = timeline[selectedIndex];

    const recentFileList = useMemo(() => {
        const files = new Set<string>();
        timeline.slice(0, selectedIndex + 1).forEach((snapshot) => {
            if (snapshot.active_file) {
                files.add(snapshot.active_file);
            }
        });
        return Array.from(files).slice(-8).reverse();
    }, [timeline, selectedIndex]);

    const recentSummaries = useMemo(() => {
        return timeline
            .slice(Math.max(0, selectedIndex - 4), selectedIndex + 1)
            .map((snapshot) => ({
                id: snapshot.id,
                summary: snapshot.summary || 'No summary',
                time: new Date(snapshot.timestamp).toLocaleTimeString(),
            }))
            .reverse();
    }, [timeline, selectedIndex]);

    useEffect(() => {
        if (typeof window !== 'undefined' && window.acquireVsCodeApi) {
            vscodeApiRef.current = window.acquireVsCodeApi();
        }
    }, []);

    const postToHost = useCallback((payload: Record<string, unknown>) => {
        const envelope = { source: 'secondcortex-shadow-graph', ...payload };
        try {
            vscodeApiRef.current?.postMessage(envelope);
        } catch {
            // Browser mode: no VS Code bridge available.
        }

        if (typeof window !== 'undefined' && window.parent && window.parent !== window) {
            window.parent.postMessage(envelope, '*');
        }
    }, []);

    const handlePreviewSelection = useCallback((index: number) => {
        const snapshot = timeline[index];
        if (!snapshot) {
            return;
        }

        setSelectedIndex(index);
        setIsPinnedInPast(index < timeline.length - 1);
        setLastEvent(`${new Date(snapshot.timestamp).toLocaleTimeString()} - ${snapshot.summary || snapshot.active_file}`);
        postToHost({ type: 'previewSnapshot', snapshotId: snapshot.id });
    }, [timeline, postToHost]);

    const handleRestore = useCallback(() => {
        if (!selectedSnapshot) {
            return;
        }
        postToHost({ type: 'restoreSnapshot', snapshotId: selectedSnapshot.id, target: selectedSnapshot.id });
    }, [postToHost, selectedSnapshot]);

    const buildGraphForSnapshot = useCallback((snapshot: SnapshotEvent | undefined): { nodes: Node[]; edges: Edge[] } => {
        if (!snapshot) {
            return { nodes: [], edges: [] };
        }

        const outNodes: Node[] = [];
        const outEdges: Edge[] = [];

        const activeFile = snapshot.active_file || 'unknown';
        const fileName = activeFile.split(/[/\\]/).pop() ?? activeFile;
        const fileNodeId = `file-${snapshot.id}`;

        outNodes.push({
            id: fileNodeId,
            data: { label: `File: ${fileName}` },
            position: { x: 0, y: 0 },
            style: NODE_STYLES.file,
        });

        const developerNodeId = `dev-${snapshot.id}`;
        outNodes.push({
            id: developerNodeId,
            data: { label: `Developer: ${snapshot.developer_name || 'Unknown'}` },
            position: { x: -260, y: -180 },
            style: NODE_STYLES.commit,
        });

        outEdges.push({
            id: `e-${developerNodeId}-${fileNodeId}`,
            source: developerNodeId,
            target: fileNodeId,
            markerEnd: { type: MarkerType.ArrowClosed },
            style: { stroke: 'rgba(255,255,255,0.45)', strokeWidth: 2 },
        });

        if (snapshot.git_branch) {
            const branchNodeId = `branch-${snapshot.id}`;
            outNodes.push({
                id: branchNodeId,
                data: { label: `Branch: ${snapshot.git_branch}` },
                position: { x: -260, y: -80 },
                style: NODE_STYLES.commit,
            });

            outEdges.push({
                id: `e-${branchNodeId}-${fileNodeId}`,
                source: branchNodeId,
                target: fileNodeId,
                animated: true,
                markerEnd: { type: MarkerType.ArrowClosed },
                style: { stroke: 'rgba(255,255,255,0.45)', strokeWidth: 2 },
            });
        }

        const timestampNodeId = `time-${snapshot.id}`;
        outNodes.push({
            id: timestampNodeId,
            data: { label: `Time: ${new Date(snapshot.timestamp).toLocaleString()}` },
            position: { x: 260, y: -80 },
            style: NODE_STYLES.entity,
        });
        outEdges.push({
            id: `e-${fileNodeId}-${timestampNodeId}`,
            source: fileNodeId,
            target: timestampNodeId,
            style: { stroke: 'rgba(255,255,255,0.35)', strokeDasharray: '4,6', strokeWidth: 1.5 },
        });

        if (snapshot.summary) {
            const reasoningNodeId = `reason-${snapshot.id}`;
            outNodes.push({
                id: reasoningNodeId,
                data: { label: snapshot.summary },
                position: { x: 0, y: 220 },
                style: NODE_STYLES.reasoning,
            });

            outEdges.push({
                id: `e-${fileNodeId}-${reasoningNodeId}`,
                source: fileNodeId,
                target: reasoningNodeId,
                animated: true,
                style: { stroke: 'rgba(255,255,255,0.75)', strokeWidth: 2.5 },
                markerEnd: { type: MarkerType.ArrowClosed },
            });
        }

        return { nodes: outNodes, edges: outEdges };
    }, []);

    useEffect(() => {
        if (!token) {
            setIsConnected(false);
            return;
        }

        let cancelled = false;
        let eventSource: EventSource | null = null;

        const startWatch = async () => {
            try {
                const authRes = await fetch(`${backendUrl}/api/sync/checkpoint`, {
                    headers: { Authorization: `Bearer ${token}` },
                });
                if (authRes.status === 401 || authRes.status === 403) {
                    setIsConnected(false);
                    if (onUnauthorized) {
                        onUnauthorized();
                    }
                    return;
                }

                if (!authRes.ok || cancelled) {
                    setIsConnected(false);
                    return;
                }

                const watchUrl = `${backendUrl}/api/sync/watch?token=${encodeURIComponent(token)}&after=0`;
                eventSource = new EventSource(watchUrl);

                eventSource.onopen = () => {
                    setIsConnected(true);
                };

                eventSource.addEventListener('team_snapshots', (event) => {
                    const message = event as MessageEvent;
                    try {
                        const parsed = JSON.parse(message.data) as { rows?: SnapshotEvent[] };
                        const nextTimeline = Array.isArray(parsed.rows) ? parsed.rows : [];
                        setTimeline(nextTimeline.slice().reverse());
                        if (nextTimeline.length > 0) {
                            setSelectedIndex((prevIndex) => {
                                if (!isPinnedInPast) {
                                    return nextTimeline.length - 1;
                                }
                                return Math.min(prevIndex, nextTimeline.length - 1);
                            });
                        }
                    } catch {
                        // ignore malformed SSE payload
                    }
                });

                eventSource.onerror = () => {
                    setIsConnected(false);
                };
            } catch {
                setIsConnected(false);
            }
        };

        startWatch();

        return () => {
            cancelled = true;
            eventSource?.close();
        };
    }, [backendUrl, token, onUnauthorized, isPinnedInPast]);

    useEffect(() => {
        const graph = buildGraphForSnapshot(selectedSnapshot);
        setNodes(graph.nodes);
        setEdges(graph.edges);
    }, [selectedSnapshot, buildGraphForSnapshot, setNodes, setEdges]);

    const selectedAgeLabel = selectedSnapshot
        ? (() => {
            const now = Date.now();
            const then = new Date(selectedSnapshot.timestamp).getTime();
            const mins = Math.max(0, Math.round((now - then) / 60000));
            if (mins < 1) return 'just now';
            if (mins < 60) return `${mins}m ago`;
            const hours = Math.floor(mins / 60);
            const remMins = mins % 60;
            return remMins ? `${hours}h ${remMins}m ago` : `${hours}h ago`;
        })()
        : 'n/a';

    return (
        <div style={{ width: '100%', height: '100vh', background: '#080808' }}>
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
                        background: 'rgba(17,17,17,0.94)',
                        border: '1px solid rgba(255,255,255,0.08)',
                        borderRadius: 16,
                        padding: '12px 20px',
                        color: '#f0f0f0',
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
                            background: isConnected ? '#f0f0f0' : '#7a7a7a',
                        }}
                    />
                    {isConnected ? 'Timeline Sync Active' : 'Offline'}
                </div>

                <div
                    style={{
                        background: 'rgba(17,17,17,0.94)',
                        border: '1px solid rgba(255,255,255,0.08)',
                        borderRadius: 16,
                        padding: '12px 24px',
                        color: 'rgba(255,255,255,0.72)',
                        fontSize: 14,
                        maxWidth: 500,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                    }}
                >
                    {selectedSnapshot ? `${selectedAgeLabel} | ${lastEvent}` : 'No snapshots captured yet'}
                </div>
            </div>

            <div
                style={{
                    position: 'absolute',
                    top: 24,
                    right: 24,
                    zIndex: 10,
                    background: 'rgba(17,17,17,0.94)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    borderRadius: 16,
                    padding: '16px 24px',
                    color: '#f0f0f0',
                    fontSize: 20,
                    fontWeight: 700,
                    letterSpacing: '-0.02em',
                }}
            >
                SecondCortex <span style={{ opacity: 0.3, fontWeight: 400 }}>| Shadow Graph</span>
            </div>

            <div
                style={{
                    position: 'absolute',
                    top: 92,
                    right: 24,
                    zIndex: 20,
                    display: 'flex',
                    gap: 8,
                    background: 'rgba(17,17,17,0.94)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: 12,
                    padding: 8,
                    backdropFilter: 'blur(12px)',
                }}
            >
                <button
                    type="button"
                    onClick={() => reactFlowInstance?.zoomIn({ duration: 200 })}
                    style={{
                        width: 38,
                        height: 38,
                        borderRadius: 8,
                        border: '1px solid rgba(255,255,255,0.2)',
                        background: 'rgba(255,255,255,0.06)',
                        color: '#f0f0f0',
                        fontSize: 22,
                        lineHeight: 1,
                        cursor: 'pointer',
                    }}
                    title="Zoom in"
                    aria-label="Zoom in"
                >
                    +
                </button>
                <button
                    type="button"
                    onClick={() => reactFlowInstance?.zoomOut({ duration: 200 })}
                    style={{
                        width: 38,
                        height: 38,
                        borderRadius: 8,
                        border: '1px solid rgba(255,255,255,0.2)',
                        background: 'rgba(255,255,255,0.06)',
                        color: '#f0f0f0',
                        fontSize: 22,
                        lineHeight: 1,
                        cursor: 'pointer',
                    }}
                    title="Zoom out"
                    aria-label="Zoom out"
                >
                    -
                </button>
                <button
                    type="button"
                    onClick={() => reactFlowInstance?.fitView({ padding: 0.25, duration: 250 })}
                    style={{
                        minWidth: 86,
                        height: 38,
                        borderRadius: 8,
                        border: '1px solid rgba(255,255,255,0.2)',
                        background: 'rgba(255,255,255,0.06)',
                        color: '#f0f0f0',
                        fontSize: 12,
                        fontWeight: 700,
                        letterSpacing: '0.08em',
                        textTransform: 'uppercase',
                        cursor: 'pointer',
                    }}
                    title="Fit graph to screen"
                    aria-label="Fit graph to screen"
                >
                    Fit
                </button>
            </div>

            <div
                style={{
                    position: 'absolute',
                    left: 24,
                    right: 24,
                    bottom: 24,
                    zIndex: 20,
                    background: 'rgba(17,17,17,0.94)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: 16,
                    padding: 14,
                    backdropFilter: 'blur(14px)',
                }}
            >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 10 }}>
                    <div style={{ color: '#f0f0f0', fontSize: 13, fontWeight: 600 }}>
                        Snapshot Slider ({timeline.length} snapshots)
                    </div>
                    <button
                        onClick={handleRestore}
                        disabled={!selectedSnapshot}
                        style={{
                            border: '1px solid rgba(255,255,255,0.35)',
                            color: '#f0f0f0',
                            background: 'rgba(255,255,255,0.08)',
                            borderRadius: 8,
                            padding: '8px 14px',
                            fontSize: 12,
                            fontWeight: 700,
                            letterSpacing: '0.02em',
                            cursor: selectedSnapshot ? 'pointer' : 'not-allowed',
                            opacity: selectedSnapshot ? 1 : 0.5,
                        }}
                    >
                        Restore
                    </button>
                </div>

                <input
                    type="range"
                    min={0}
                    max={Math.max(0, timeline.length - 1)}
                    value={Math.min(selectedIndex, Math.max(0, timeline.length - 1))}
                    onChange={(e) => {
                        const idx = Number(e.target.value);
                        handlePreviewSelection(idx);
                    }}
                    style={{ width: '100%' }}
                    disabled={timeline.length === 0}
                />

                <div style={{ display: 'flex', gap: 6, marginTop: 8, overflowX: 'auto', paddingBottom: 2 }}>
                    {timeline.map((snapshot, idx) => (
                        <button
                            key={snapshot.id}
                            onClick={() => handlePreviewSelection(idx)}
                            title={new Date(snapshot.timestamp).toLocaleString()}
                            style={{
                                width: 10,
                                height: 10,
                                borderRadius: '50%',
                                border: 'none',
                                flex: '0 0 auto',
                                cursor: 'pointer',
                                background: idx === selectedIndex ? '#f0f0f0' : 'rgba(148,163,184,0.55)',
                                boxShadow: idx === selectedIndex ? '0 0 0 3px rgba(255,255,255,0.2)' : 'none',
                            }}
                        />
                    ))}
                </div>

                <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                    <div style={{ background: 'rgba(8,8,8,0.66)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 10, padding: 10 }}>
                        <div style={{ fontSize: 12, color: '#f0f0f0', marginBottom: 6, fontWeight: 700 }}>Files At This Point</div>
                        {recentFileList.length === 0 ? (
                            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)' }}>No files yet</div>
                        ) : (
                            recentFileList.map((file) => (
                                <div key={file} style={{ fontSize: 12, color: '#f0f0f0', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                    {file}
                                </div>
                            ))
                        )}
                    </div>

                    <div style={{ background: 'rgba(8,8,8,0.66)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 10, padding: 10 }}>
                        <div style={{ fontSize: 12, color: '#f0f0f0', marginBottom: 6, fontWeight: 700 }}>Recent Summaries</div>
                        {recentSummaries.length === 0 ? (
                            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)' }}>No summary timeline</div>
                        ) : (
                            recentSummaries.map((item) => (
                                <div key={item.id} style={{ marginBottom: 5 }}>
                                    <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.45)' }}>{item.time}</div>
                                    <div style={{ fontSize: 12, color: '#f0f0f0', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.summary}</div>
                                </div>
                            ))
                        )}
                    </div>
                </div>
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
                onInit={setReactFlowInstance}
                style={{ background: '#080808' }}
            >
                <Background color="rgba(255,255,255,0.14)" gap={24} size={1} variant={BackgroundVariant.Dots} />
                <MiniMap
                    nodeColor={(node) => {
                        if (node.id.startsWith('reason')) return '#f0f0f0';
                        if (node.id.startsWith('file')) return '#b4b4b4';
                        if (node.id.startsWith('branch')) return '#8a8a8a';
                        return '#636363';
                    }}
                    maskColor="rgba(8,8,8,0.86)"
                    style={{
                        background: 'rgba(17,17,17,0.85)',
                        backdropFilter: 'blur(12px)',
                        border: '1px solid rgba(255,255,255,0.1)',
                        borderRadius: 16,
                        boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
                    }}
                />
            </ReactFlow>

            <style>{`
                :root {
                    color-scheme: dark;
                }
                body {
                    margin: 0;
                    padding: 0;
                    background: #080808;
                    color: #f0f0f0;
                    overflow: hidden;
                    font-family: var(--font-display);
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
