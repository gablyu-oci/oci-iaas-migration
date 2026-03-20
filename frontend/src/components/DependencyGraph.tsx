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

export default function DependencyGraph({ data }: Props) {
  const { nodes: rfNodes, edges: rfEdges } = useMemo(() => {
    try {
      const parsed = JSON.parse(data);
      const rawNodes: RawNode[] = parsed.nodes || [];
      const rawEdges: RawEdge[] = parsed.edges || [];

      const nodes: Node[] = rawNodes.map((n, i) => ({
        id: n.id,
        data: { label: n.id.replace(/_/g, ' ') },
        position: { x: (i % 5) * 220 + 50, y: Math.floor(i / 5) * 120 + 50 },
        style: {
          background: n.service?.includes('lambda')
            ? 'rgba(251,191,36,0.12)'
            : n.service?.includes('s3')
              ? 'rgba(96,165,250,0.12)'
              : '#192236',
          border: `1px solid ${
            n.service?.includes('lambda')
              ? 'rgba(251,191,36,0.35)'
              : n.service?.includes('s3')
                ? 'rgba(96,165,250,0.35)'
                : '#253552'
          }`,
          borderRadius: '8px',
          padding: '10px',
          fontSize: '12px',
          color: '#e2e8f0',
          fontFamily: '"IBM Plex Mono", ui-monospace, monospace',
        },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      }));

      const edges: Edge[] = rawEdges.map((e, i) => ({
        id: `e-${i}`,
        source: e.source,
        target: e.target,
        label: e.edge_type || '',
        animated: e.edge_type === 'network',
        style: {
          stroke: e.edge_type === 'network' ? '#60a5fa' : '#2f4166',
        },
        labelStyle: { fill: '#64748b', fontSize: 11 },
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
      style={{ height: '500px', borderRadius: '8px', overflow: 'hidden', border: '1px solid var(--color-fence)' }}
    >
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        fitView
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
