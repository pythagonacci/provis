import React, { useMemo } from 'react';
import { GitBranch } from 'lucide-react';
import { GraphNode, GraphEdge } from '@/types/capability';

type SwimlaneFlowProps = {
  focus: string | null;
  highlighted?: string[];
  onSelect?: (id: string) => void;
  // This will be populated with real data from the backend
  nodes?: GraphNode[];
  edges?: GraphEdge[];
};

// Placeholder graph layout - will be replaced with real data
function buildPlaceholderGraph(focus: string | null) {
  const layout: GraphNode[] = [
    { id: "app/page.tsx", label: "page.tsx", x: 80, y: 170 },
    { id: "pages/api/compileDeck.ts", label: "compileDeck.ts", x: 250, y: 170 },
    { id: "deck/compile.ts", label: "compile.ts", x: 430, y: 170 },
    { id: "slides/buildOutline.ts", label: "buildOutline.ts", x: 620, y: 120 },
    { id: "templates/mdToHtml.ts", label: "mdToHtml.ts", x: 620, y: 220 },
    { id: "content/sections.ts", label: "sections.ts", x: 800, y: 120 },
    { id: "styles/print.css", label: "print.css", x: 800, y: 240 },
  ];
  const edges: GraphEdge[] = [
    { from: "app/page.tsx", to: "pages/api/compileDeck.ts" },
    { from: "pages/api/compileDeck.ts", to: "deck/compile.ts" },
    { from: "deck/compile.ts", to: "slides/buildOutline.ts" },
    { from: "deck/compile.ts", to: "templates/mdToHtml.ts" },
    { from: "slides/buildOutline.ts", to: "content/sections.ts" },
    { from: "deck/compile.ts", to: "styles/print.css" },
  ];
  return { nodes: layout, edges, focus };
}

export function SwimlaneFlow({ focus, highlighted = [], onSelect, nodes, edges }: SwimlaneFlowProps) {
  // Use real data if available, otherwise fall back to placeholder
  const graph = useMemo(() => {
    if (nodes && edges) {
      return { nodes, edges, focus };
    }
    return buildPlaceholderGraph(focus);
  }, [focus, nodes, edges]);

  return (
    <div className="relative h-[360px] w-full rounded-2xl border border-white/10 bg-gradient-to-b from-white/5 to-white/0 p-3 backdrop-blur">
      <svg className="h-full w-full">
        {graph.edges.map((e, i) => {
          const a = graph.nodes.find((n) => n.id === e.from)!;
          const b = graph.nodes.find((n) => n.id === e.to)!;
          const edgeHot = [focus, ...highlighted].includes(e.from) || [focus, ...highlighted].includes(e.to);
          return (
            <line 
              key={i} 
              x1={a.x} 
              y1={a.y} 
              x2={b.x} 
              y2={b.y} 
              stroke="currentColor" 
              className={edgeHot ? "text-emerald-300" : "text-white/30"} 
              strokeWidth={edgeHot ? 2 : 1.5} 
              markerEnd="url(#arrow)" 
            />
          );
        })}
        <defs>
          <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
            <path d="M0,0 L0,6 L6,3 z" fill="currentColor" className="text-white/30" />
          </marker>
        </defs>
        {graph.nodes.map((n) => {
          const isFocus = focus === n.id;
          const isHi = highlighted.includes(n.id);
          return (
            <g 
              key={n.id} 
              transform={`translate(${n.x - 36}, ${n.y - 18})`} 
              onClick={() => onSelect?.(n.id)} 
              style={{ cursor: 'pointer' }}
            >
              <rect 
                width="120" 
                height="32" 
                rx="8" 
                stroke="currentColor" 
                strokeWidth={isFocus || isHi ? 2 : 1} 
                className={`fill-white/10 ${isFocus || isHi ? 'text-emerald-300' : 'text-white/20'}`} 
              />
              <text x="10" y="20" className="fill-white text-xs">{n.label}</text>
            </g>
          );
        })}
      </svg>
      <div className="absolute left-3 top-3 flex items-center gap-2 text-xs text-white/70">
        <GitBranch size={14} /> 
        {nodes && edges ? 'Repository flow' : 'Placeholder flow - waiting for real data'}
      </div>
    </div>
  );
}
