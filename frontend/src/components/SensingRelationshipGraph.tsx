import React, { useMemo, useCallback, useState } from 'react';
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
import type { TechRelationshipMap, SensingRadarItem, TechRelationship } from '@/lib/api';
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
  'enables': '#22c55e',
  'competes_with': '#ef4444',
  'integrates_with': '#a855f7',
  'evolves_from': '#3b82f6',
};

const RELATIONSHIP_LABELS: Record<string, string> = {
  'enables': 'Enables',
  'competes_with': 'Competes',
  'integrates_with': 'Integrates',
  'evolves_from': 'Evolves from',
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
  const [selectedEdge, setSelectedEdge] = useState<TechRelationship | null>(null);

  const { initialNodes, initialEdges, clusterInfo, relLookup } = useMemo(() => {
    // Build lookup for radar items
    const radarLookup = new Map<string, SensingRadarItem>();
    radarItems.forEach((item) => {
      radarLookup.set(item.name.toLowerCase().trim(), item);
    });

    // Build edge -> relationship lookup for tooltip
    const lookup = new Map<string, TechRelationship>();
    relationships.relationships.forEach((rel, idx) => {
      lookup.set(`e-${idx}`, rel);
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
      const label = RELATIONSHIP_LABELS[rel.relationship_type] || rel.relationship_type;
      const articleSuffix = rel.article_count ? ` (${rel.article_count})` : '';
      return {
        id: `e-${idx}`,
        source: rel.source_tech,
        target: rel.target_tech,
        label: `${label}${articleSuffix}`,
        type: 'default',
        animated: rel.confidence === 'high',
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
      relLookup: lookup,
    };
  }, [relationships, radarItems]);

  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      setSelectedEdge(null);
      onTechClick?.(node.id);
    },
    [onTechClick],
  );

  const onEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => {
      const rel = relLookup.get(edge.id);
      setSelectedEdge(rel || null);
    },
    [relLookup],
  );

  const onPaneClick = useCallback(() => {
    setSelectedEdge(null);
  }, []);

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
            <Badge
              key={cluster.cluster_name}
              variant="outline"
              className="text-xs"
              title={`${cluster.theme}${cluster.rationale ? '\n' + cluster.rationale : ''}`}
            >
              {cluster.cluster_name} ({cluster.technologies.length})
            </Badge>
          ))}
        </div>
      )}

      {/* Evidence tooltip */}
      {selectedEdge && (
        <div className="mx-2 p-3 rounded-lg border bg-muted/50 text-xs space-y-1">
          <div className="flex items-center gap-2 font-medium">
            <span>{selectedEdge.source_tech}</span>
            <span className="text-muted-foreground">
              {RELATIONSHIP_LABELS[selectedEdge.relationship_type] || selectedEdge.relationship_type}
            </span>
            <span>{selectedEdge.target_tech}</span>
            <Badge variant="outline" className="ml-auto text-[10px]">
              {selectedEdge.confidence} confidence
            </Badge>
            {selectedEdge.article_count > 0 && (
              <Badge variant="secondary" className="text-[10px]">
                {selectedEdge.article_count} article{selectedEdge.article_count !== 1 ? 's' : ''}
              </Badge>
            )}
          </div>
          {selectedEdge.evidence && (
            <p className="text-muted-foreground leading-relaxed">{selectedEdge.evidence}</p>
          )}
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
          onEdgeClick={onEdgeClick}
          onPaneClick={onPaneClick}
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
        {!selectedEdge && (
          <span className="ml-auto italic">Click an edge to see evidence</span>
        )}
      </div>
    </div>
  );
};

export default SensingRelationshipGraph;
