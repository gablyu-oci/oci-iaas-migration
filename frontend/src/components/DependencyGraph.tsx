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
            ? '#fef3c7'
            : n.service?.includes('s3')
              ? '#dbeafe'
              : '#f3f4f6',
          border: '1px solid #d1d5db',
          borderRadius: '8px',
          padding: '10px',
          fontSize: '12px',
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
          stroke: e.edge_type === 'network' ? '#60a5fa' : '#9ca3af',
        },
      }));

      return { nodes, edges };
    } catch {
      return { nodes: [] as Node[], edges: [] as Edge[] };
    }
  }, [data]);

  if (!rfNodes.length) {
    return (
      <p className="text-gray-500 text-center py-8">
        No graph data available.
      </p>
    );
  }

  return (
    <div style={{ height: '500px' }} className="border rounded-lg overflow-hidden">
      <ReactFlow nodes={rfNodes} edges={rfEdges} fitView>
        <Background />
        <Controls />
        <MiniMap />
      </ReactFlow>
    </div>
  );
}
