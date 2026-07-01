import React, { useEffect, useRef, useCallback } from 'react';

// ── Types ──
export interface GraphNode {
  id: string;
  label: string;
  type: 'user' | 'company' | 'enterprise';
  avatar?: string;
  trustScore?: number;
  [key: string]: any;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  trustLevel: number; // 0–1, mapped to stroke-width
  label?: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

interface ForceGraphProps {
  data: GraphData | null;
  loading?: boolean;
  highlightIds?: Set<string>;
  onNodeClick?: (node: GraphNode) => void;
  className?: string;
}

// ── D3 CDN URL ──
const D3_CDN = 'https://d3js.org/d3.v7.min.js';

/**
 * Load D3 from CDN once, return a promise resolving to the d3 object.
 */
function loadD3(): Promise<typeof import('d3')> {
  if ((window as any).d3) return Promise.resolve((window as any).d3);

  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = D3_CDN;
    script.async = true;
    script.onload = () => resolve((window as any).d3);
    script.onerror = () => reject(new Error('Failed to load D3 from CDN'));
    document.head.appendChild(script);
  });
}

// ── Component ──
const ForceGraph: React.FC<ForceGraphProps> = ({
  data,
  loading = false,
  highlightIds,
  onNodeClick,
  className = '',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const simulationRef = useRef<any>(null);
  const d3Ref = useRef<any>(null);

  // Load D3
  useEffect(() => {
    let cancelled = false;
    loadD3()
      .then((d3) => {
        if (!cancelled) d3Ref.current = d3;
      })
      .catch((err) => console.error('[ForceGraph]', err));
    return () => { cancelled = true; };
  }, []);

  // Render graph when data or D3 changes
  const renderGraph = useCallback(() => {
    const d3 = d3Ref.current;
    if (!d3 || !data || !containerRef.current) return;

    // Clear previous
    const container = containerRef.current;
    container.innerHTML = '';

    const { width, height } = container.getBoundingClientRect();
    const svg = d3
      .select(container)
      .append('svg')
      .attr('width', width)
      .attr('height', height)
      .style('cursor', 'grab');

    svgRef.current = svg.node();

    // ── Zoom & Pan ──
    const g = svg.append('g');
    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 6])
      .on('zoom', (event: any) => g.attr('transform', event.transform));
    svg.call(zoom);

    // ── Simulation ──
    const nodes = data.nodes.map((n) => ({ ...n }));
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    const edges = data.edges.map((e) => ({
      source: e.source,
      target: e.target,
      relation: e.relation,
      trustLevel: e.trustLevel,
      label: e.label,
    }));

    const simulation = d3
      .forceSimulation(nodes)
      .force(
        'link',
        d3
          .forceLink(edges)
          .id((d: any) => d.id)
          .distance(120)
      )
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide(30));

    simulationRef.current = simulation;

    // ── Links ──
    const link = g
      .append('g')
      .attr('stroke', '#64748b')
      .attr('stroke-opacity', 0.5)
      .selectAll<SVGLineElement, any>('line')
      .data(edges)
      .join('line')
      .attr('stroke-width', (d: any) => Math.max(0.5, d.trustLevel * 4));

    // ── Link labels ──
    const linkLabel = g
      .append('g')
      .selectAll<SVGTextElement, any>('text')
      .data(edges)
      .join('text')
      .text((d: any) => d.label || d.relation)
      .attr('font-size', 10)
      .attr('fill', '#94a3b8')
      .attr('text-anchor', 'middle')
      .attr('dy', -4);

    // ── Nodes ──
    const nodeGroup = g
      .append('g')
      .selectAll<SVGGElement, any>('g')
      .data(nodes)
      .join('g')
      .attr('cursor', 'pointer')
      .call(
        d3
          .drag<SVGGElement, any>()
          .on('start', (event: any, d: any) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on('drag', (event: any, d: any) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on('end', (event: any, d: any) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      );

    // Node circles
    nodeGroup
      .append('circle')
      .attr('r', (d: any) => (d.type === 'enterprise' ? 18 : 12))
      .attr('fill', (d: any) => {
        if (highlightIds?.has(d.id)) return '#f59e0b';
        return d.type === 'enterprise' ? '#3b82f6' : d.type === 'company' ? '#10b981' : '#8b5cf6';
      })
      .attr('stroke', (d: any) => (highlightIds?.has(d.id) ? '#fbbf24' : '#1e293b'))
      .attr('stroke-width', (d: any) => (highlightIds?.has(d.id) ? 3 : 1.5));

    // Node labels
    nodeGroup
      .append('text')
      .text((d: any) => d.label)
      .attr('dx', 16)
      .attr('dy', 4)
      .attr('font-size', 12)
      .attr('fill', '#e2e8f0')
      .attr('pointer-events', 'none')
      .style('text-shadow', '0 1px 3px rgba(0,0,0,0.8)');

    // Trust score badge
    nodeGroup
      .filter((d: any) => d.trustScore !== undefined)
      .append('text')
      .text((d: any) => `${Math.round((d.trustScore || 0) * 100)}`)
      .attr('dx', -8)
      .attr('dy', 4)
      .attr('font-size', 8)
      .attr('fill', '#fff')
      .attr('text-anchor', 'middle')
      .attr('pointer-events', 'none');

    // Click handler
    nodeGroup.on('click', (_event: any, d: any) => {
      onNodeClick?.(d);
    });

    // ── Tick ──
    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y);

      linkLabel
        .attr('x', (d: any) => (d.source.x + d.target.x) / 2)
        .attr('y', (d: any) => (d.source.y + d.target.y) / 2);

      nodeGroup.attr('transform', (d: any) => `translate(${d.x},${d.y})`);
    });

    // ── Initial zoom fit ──
    setTimeout(() => {
      const bounds = (svg.node() as any)?.getBBox();
      if (bounds) {
        const scale = Math.min(width / (bounds.width + 60), height / (bounds.height + 60), 1.5);
        const tx = (width - bounds.width * scale) / 2 - bounds.x * scale;
        const ty = (height - bounds.height * scale) / 2 - bounds.y * scale;
        svg
          .transition()
          .duration(500)
          .call(zoom.transform as any, d3.zoomIdentity.translate(tx, ty).scale(scale));
      }
    }, 100);
  }, [data, highlightIds, onNodeClick]);

  // Re-render when data or D3 changes
  useEffect(() => {
    if (d3Ref.current && data) renderGraph();
  }, [data, renderGraph]);

  // Watch highlightIds — update strokes dynamically without full re-render
  useEffect(() => {
    const d3 = d3Ref.current;
    if (!d3 || !svgRef.current || !data) return;

    const svg = d3.select(svgRef.current);
    svg
      .selectAll<SVGCircleElement, any>('circle')
      .attr('fill', (d: any) => {
        if (highlightIds?.has(d.id)) return '#f59e0b';
        return d.type === 'enterprise' ? '#3b82f6' : d.type === 'company' ? '#10b981' : '#8b5cf6';
      })
      .attr('stroke', (d: any) => (highlightIds?.has(d.id) ? '#fbbf24' : '#1e293b'))
      .attr('stroke-width', (d: any) => (highlightIds?.has(d.id) ? 3 : 1.5));
  }, [highlightIds, data]);

  // Resize observer
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver(() => {
      if (data) renderGraph();
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [data, renderGraph]);

  return (
    <div
      ref={containerRef}
      className={`relative w-full h-full overflow-hidden bg-slate-900 ${className}`}
    >
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-900/60 z-10">
          <div className="flex flex-col items-center gap-3">
            <div className="w-8 h-8 border-2 border-sky-400 border-t-transparent rounded-full animate-spin" />
            <span className="text-slate-300 text-sm">加载关系网络...</span>
          </div>
        </div>
      )}
      {!loading && !data && (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-slate-500 text-sm">暂无关系数据</span>
        </div>
      )}
    </div>
  );
};

export default ForceGraph;
