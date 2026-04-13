import React, { useMemo, useCallback } from 'react';
import ReactFlow, {
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
} from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from 'dagre';
import type { TechRelationshipMap, SensingRadarItem } from '@/lib/api';
import { Badge } from '@/components/ui/badge';

interface Props {
  relationships: TechRelationshipMap;
  radarItems: SensingRadarItem[];
  onTechClick?: (name: string) => void;
}

const QUADRANT_COLORS: Record<string, string> = {
  'Techniques': '#1ebccd',
  'Platforms': '#f38a3e',
  'Tools': '#86b82a',
  'Languages & Frameworks': '#b32059',
};

const RELATIONSHIP_COLORS: Record<string, string> = {
  'builds_on': '#3b82f6',
  'competes_with': '#ef4444',
  'enables': '#22c55e',
  'integrates_with': '#a855f7',
  'alternative_to': '#f97316',
};

const RELATIONSHIP_LABELS: Record<string, string> = {
  'builds_on': 'Builds on',
  'competes_with': 'Competes',
  'enables': 'Enables',
  'integrates_with': 'Integrates',
  'alternative_to': 'Alternative',
};

function getLayoutedElements(
  nodes: Node[],
  edges: Edge[],
  direction = 'LR',
): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 60, ranksep: 100 });

  nodes.forEach((node) => {
    g.setNode(node.id, { width: 160, height: 50 });
  });

  edges.forEach((edge) => {
    g.setEdge(edge.source, edge.target);
  });

  dagre.layout(g);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = g.node(node.id);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - 80,
        y: nodeWithPosition.y - 25,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
}

const SensingRelationshipGraph: React.FC<Props> = ({
  relationships,
  radarItems,
  onTechClick,
}) => {
  const { initialNodes, initialEdges, clusterInfo } = useMemo(() => {
    // Build lookup for radar items
    const radarLookup = new Map<string, SensingRadarItem>();
    radarItems.forEach((item) => {
      radarLookup.set(item.name.toLowerCase().trim(), item);
    });

    // Create nodes for technologies that appear in relationships
    const techsInGraph = new Set<string>();
    relationships.relationships.forEach((rel) => {
      techsInGraph.add(rel.source_tech);
      techsInGraph.add(rel.target_tech);
    });

    const nodes: Node[] = [];
    techsInGraph.forEach((techName) => {
      const radarItem = radarLookup.get(techName.toLowerCase().trim());
      const quadrantColor = radarItem
        ? QUADRANT_COLORS[radarItem.quadrant] || '#888'
        : '#888';
      const signalStrength = radarItem?.signal_strength || 0.3;

      nodes.push({
        id: techName,
        data: {
          label: techName,
          quadrant: radarItem?.quadrant || 'Unknown',
          ring: radarItem?.ring || 'Unknown',
          signalStrength,
        },
        position: { x: 0, y: 0 },
        style: {
          background: quadrantColor + '20',
          border: `2px solid ${quadrantColor}`,
          borderRadius: '8px',
          padding: '8px 12px',
          fontSize: '11px',
          fontWeight: 600,
          color: 'inherit',
          width: 160,
          textAlign: 'center' as const,
        },
      });
    });

    // Create edges
    const edges: Edge[] = relationships.relationships.map((rel, idx) => {
      const color = RELATIONSHIP_COLORS[rel.relationship_type] || '#888';
      return {
        id: `e-${idx}`,
        source: rel.source_tech,
        target: rel.target_tech,
        label: RELATIONSHIP_LABELS[rel.relationship_type] || rel.relationship_type,
        type: 'default',
        animated: rel.strength > 0.7,
        style: {
          stroke: color,
          strokeWidth: Math.max(1, rel.strength * 3),
        },
        labelStyle: {
          fontSize: 9,
          fill: color,
          fontWeight: 500,
        },
        labelBgStyle: {
          fill: 'var(--background, #fff)',
          fillOpacity: 0.8,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color,
          width: 15,
          height: 15,
        },
      };
    });

    // Layout with dagre
    const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
      nodes,
      edges,
    );

    return {
      initialNodes: layoutedNodes,
      initialEdges: layoutedEdges,
      clusterInfo: relationships.clusters || [],
    };
  }, [relationships, radarItems]);

  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      onTechClick?.(node.id);
    },
    [onTechClick],
  );

  if (!relationships.relationships.length) {
    return (
      <div className="flex items-center justify-center h-64 text-muted-foreground">
        No technology relationships detected in this report.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* Legend */}
      <div className="flex flex-wrap gap-3 px-2">
        <span className="text-xs font-medium text-muted-foreground">Relationships:</span>
        {Object.entries(RELATIONSHIP_LABELS).map(([type, label]) => (
          <span key={type} className="flex items-center gap-1 text-xs">
            <span
              className="w-4 h-0.5 inline-block rounded"
              style={{ backgroundColor: RELATIONSHIP_COLORS[type] }}
            />
            {label}
          </span>
        ))}
      </div>

      {/* Clusters */}
      {clusterInfo.length > 0 && (
        <div className="flex flex-wrap gap-2 px-2">
          <span className="text-xs font-medium text-muted-foreground">Clusters:</span>
          {clusterInfo.map((cluster) => (
            <Badge key={cluster.cluster_name} variant="outline" className="text-xs" title={cluster.theme}>
              {cluster.cluster_name} ({cluster.technologies.length})
            </Badge>
          ))}
        </div>
      )}

      {/* Graph */}
      <div className="flex-1 min-h-[400px] border rounded-lg overflow-hidden">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.3}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={20} size={1} />
          <Controls showInteractive={false} />
          <MiniMap
            nodeStrokeWidth={2}
            pannable
            zoomable
            style={{ height: 80, width: 120 }}
          />
        </ReactFlow>
      </div>

      {/* Stats */}
      <div className="flex gap-4 px-2 text-xs text-muted-foreground">
        <span>{relationships.relationships.length} relationships</span>
        <span>{new Set([...relationships.relationships.map(r => r.source_tech), ...relationships.relationships.map(r => r.target_tech)]).size} technologies</span>
        <span>{clusterInfo.length} clusters</span>
      </div>
    </div>
  );
};

export default SensingRelationshipGraph;
