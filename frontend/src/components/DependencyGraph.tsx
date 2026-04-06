import { useMemo } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  Position,
} from 'reactflow';
import 'reactflow/dist/style.css';

interface Props {
  data: string; // JSON string with { nodes, edges }
}

interface RawNode {
  id: string;
  service?: string;
}

interface RawEdge {
  source: string;
  target: string;
  edge_type?: string;
}

/**
 * Simple layered layout: assign each node a depth based on longest path
 * from a root, then space nodes within each layer.
 */
function computeLayout(rawNodes: RawNode[], rawEdges: RawEdge[]) {
  const nodeIds = new Set(rawNodes.map((n) => n.id));
  const children: Record<string, string[]> = {};
  const inDegree: Record<string, number> = {};

  for (const id of nodeIds) {
    children[id] = [];
    inDegree[id] = 0;
  }
  for (const e of rawEdges) {
    if (nodeIds.has(e.source) && nodeIds.has(e.target)) {
      children[e.source].push(e.target);
      inDegree[e.target] = (inDegree[e.target] || 0) + 1;
    }
  }

  // BFS from roots (nodes with no incoming edges)
  const depth: Record<string, number> = {};
  const roots = rawNodes.filter((n) => (inDegree[n.id] || 0) === 0).map((n) => n.id);
  // If no roots (cycle), just pick all nodes
  const queue: string[] = roots.length > 0 ? [...roots] : rawNodes.map((n) => n.id);
  for (const id of queue) {
    if (!(id in depth)) depth[id] = 0;
  }

  let head = 0;
  while (head < queue.length) {
    const id = queue[head++];
    for (const child of children[id] || []) {
      const newDepth = depth[id] + 1;
      if (!(child in depth) || depth[child] < newDepth) {
        depth[child] = newDepth;
        queue.push(child);
      }
    }
  }

  // Assign positions not yet covered (disconnected nodes)
  let maxDepth = 0;
  for (const n of rawNodes) {
    if (!(n.id in depth)) depth[n.id] = 0;
    if (depth[n.id] > maxDepth) maxDepth = depth[n.id];
  }

  // Group by layer
  const layers: Record<number, string[]> = {};
  for (const n of rawNodes) {
    const d = depth[n.id];
    if (!layers[d]) layers[d] = [];
    layers[d].push(n.id);
  }

  // Assign positions
  const X_SPACING = 260;
  const Y_SPACING = 90;
  const positions: Record<string, { x: number; y: number }> = {};

  for (let d = 0; d <= maxDepth; d++) {
    const layer = layers[d] || [];
    const layerHeight = layer.length * Y_SPACING;
    const startY = -layerHeight / 2;
    layer.forEach((id, i) => {
      positions[id] = { x: d * X_SPACING + 50, y: startY + i * Y_SPACING + 50 };
    });
  }

  return positions;
}

function nodeColor(service?: string): { bg: string; border: string } {
  if (!service) return { bg: '#192236', border: '#253552' };
  const s = service.toLowerCase();
  if (s.includes('ec2') || s.includes('instance') || s.includes('compute'))
    return { bg: 'rgba(251,146,60,0.12)', border: 'rgba(251,146,60,0.35)' };
  if (s.includes('loadbalancer') || s.includes('elb') || s.includes('listener') || s.includes('target'))
    return { bg: 'rgba(96,165,250,0.12)', border: 'rgba(96,165,250,0.35)' };
  if (s.includes('subnet') || s.includes('vpc') || s.includes('route') || s.includes('gateway') || s.includes('nacl') || s.includes('acl'))
    return { bg: 'rgba(74,222,128,0.10)', border: 'rgba(74,222,128,0.30)' };
  if (s.includes('security'))
    return { bg: 'rgba(251,191,36,0.12)', border: 'rgba(251,191,36,0.35)' };
  if (s.includes('volume') || s.includes('ebs') || s.includes('storage'))
    return { bg: 'rgba(168,85,247,0.12)', border: 'rgba(168,85,247,0.35)' };
  if (s.includes('autoscaling') || s.includes('launch'))
    return { bg: 'rgba(251,146,60,0.08)', border: 'rgba(251,146,60,0.25)' };
  return { bg: '#192236', border: '#253552' };
}

export default function DependencyGraph({ data }: Props) {
  const { nodes: rfNodes, edges: rfEdges } = useMemo(() => {
    try {
      const parsed = JSON.parse(data);
      const rawNodes: RawNode[] = parsed.nodes || [];
      const rawEdges: RawEdge[] = parsed.edges || [];

      const positions = computeLayout(rawNodes, rawEdges);

      const nodes: Node[] = rawNodes.map((n) => {
        const colors = nodeColor(n.service);
        return {
          id: n.id,
          data: { label: n.id.replace(/_/g, ' ') },
          position: positions[n.id] || { x: 0, y: 0 },
          style: {
            background: colors.bg,
            border: `1px solid ${colors.border}`,
            borderRadius: '8px',
            padding: '8px 10px',
            fontSize: '11px',
            color: '#e2e8f0',
            fontFamily: '"IBM Plex Mono", ui-monospace, monospace',
            maxWidth: '200px',
            whiteSpace: 'nowrap' as const,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          },
          sourcePosition: Position.Right,
          targetPosition: Position.Left,
        };
      });

      const edges: Edge[] = rawEdges.map((e, i) => ({
        id: `e-${i}`,
        source: e.source,
        target: e.target,
        label: e.edge_type === 'network' ? 'network' : e.edge_type === 'cloudtrail' ? 'cloudtrail' : '',
        animated: e.edge_type === 'network',
        style: {
          stroke: e.edge_type === 'network' ? '#60a5fa'
            : e.edge_type === 'cfn-structural' ? '#4ade80'
            : '#2f4166',
        },
        labelStyle: { fill: '#64748b', fontSize: 10 },
        labelBgStyle: { fill: '#0d1221', fillOpacity: 0.85 },
      }));

      return { nodes, edges };
    } catch {
      return { nodes: [] as Node[], edges: [] as Edge[] };
    }
  }, [data]);

  if (!rfNodes.length) {
    return (
      <div className="empty-state">
        <p>No graph data available.</p>
      </div>
    );
  }

  return (
    <div
      style={{ height: Math.min(800, Math.max(400, rfNodes.length * 18)), borderRadius: '8px', overflow: 'hidden', border: '1px solid var(--color-fence)' }}
    >
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.1}
        maxZoom={2}
        style={{ background: '#0d1221' }}
      >
        <Background color="#1e2d45" gap={20} />
        <Controls
          style={{
            background: '#121828',
            border: '1px solid #253552',
            borderRadius: '8px',
          }}
        />
        <MiniMap
          style={{ background: '#0d1221', border: '1px solid #253552' }}
          nodeColor={(n) => (n.style?.background as string) ?? '#192236'}
          maskColor="rgba(8,11,20,0.7)"
        />
      </ReactFlow>
    </div>
  );
}
