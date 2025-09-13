'use client';

import { useMemo } from 'react';
import { GitBranch } from 'lucide-react';
import { Module, Endpoint, Model, Capability } from '@/lib/api';

interface FlowGraphProps {
  scan: {
    modules: Record<string, Module>;
    endpoints: Endpoint[];
    models: Model[];
    capabilities: Capability[];
  };
  focus: string | null;
  hi?: string[];
  onSelect?: (id: string) => void;
}

function buildLayout(scan: FlowGraphProps['scan']) {
  const laneY: { [k: string]: number } = {
    ui: 80,
    api: 170,
    service: 260,
    data: 350
  };
  
  const mods = Object.values(scan.modules);
  const nodes: any[] = [];
  
  const push = (items: any[], y: number) => {
    const g = 140;
    items.forEach((it, i) => 
      nodes.push({ id: it.id, label: it.label, x: 100 + i * g, y, layer: it.lane })
    );
  };

  // UI layer
  push(mods.filter(m => m.layer === "ui").map(m => ({
    id: m.id,
    label: m.path.split("/").pop() || m.path,
    lane: "ui"
  })), laneY.ui);

  // API layer
  push([
    ...mods.filter(m => m.layer === "api").map(m => ({
      id: m.id,
      label: m.path.split("/").pop() || m.path,
      lane: "api"
    })),
    ...scan.endpoints.map(e => ({
      id: `endpoint:${e.method} ${e.path}`,
      label: `${e.method} ${e.path}`,
      lane: "api"
    }))
  ], laneY.api);

  // Service layer
  push(mods.filter(m => m.layer === "service").map(m => ({
    id: m.id,
    label: m.path.split("/").pop() || m.path,
    lane: "service"
  })), laneY.service);

  // Data layer
  push([
    ...mods.filter(m => m.layer === "data").map(m => ({
      id: m.id,
      label: m.path.split("/").pop() || m.path,
      lane: "data"
    })),
    ...scan.models.map(md => ({
      id: `model:${md.id}`,
      label: md.id,
      lane: "model"
    }))
  ], laneY.data);

  // Build edges
  const edges: any[] = [];
  
  // Module imports
  mods.forEach(m => {
    m.imports?.forEach(imp => {
      if (!imp.startsWith("pkg:") && scan.modules[imp]) {
        edges.push({ from: m.id, to: imp });
      }
    });
  });

  // Endpoint to handler
  scan.endpoints.forEach(e => {
    edges.push({ from: `endpoint:${e.method} ${e.path}`, to: e.handlerFile });
  });

  // Models to files
  scan.models.forEach(md => {
    if (md.file && scan.modules[md.file]) {
      edges.push({ from: md.file, to: `model:${md.id}` });
    }
  });

  return { nodes, edges };
}

export default function FlowGraph({ scan, focus, hi = [], onSelect }: FlowGraphProps) {
  const g = useMemo(() => buildLayout(scan), [scan]);
  
  const lanes: { [k: string]: any } = {
    ui: { l: "UI", I: "Globe" },
    api: { l: "API", I: "Server" },
    service: { l: "Services", I: "Activity" },
    data: { l: "Data", I: "Database" }
  };

  return (
    <div className="relative h-[380px] w-full rounded-2xl border border-white/10 bg-gradient-to-b from-white/5 to-white/0 p-3">
      <svg className="h-full w-full">
        {/* Lane separators */}
        {[80, 170, 260, 350].map((y, i) => (
          <line 
            key={i} 
            x1={0} 
            y1={y} 
            x2={1200} 
            y2={y} 
            stroke="currentColor" 
            className="text-white/10" 
            strokeWidth={1}
          />
        ))}

        {/* Edges */}
        {g.edges.map((e, i) => {
          const a = g.nodes.find(n => n.id === e.from);
          const b = g.nodes.find(n => n.id === e.to);
          if (!a || !b) return null;
          
          const hot = [focus, ...hi].includes(e.from) || [focus, ...hi].includes(e.to);
          return (
            <line 
              key={i} 
              x1={a.x} 
              y1={a.y} 
              x2={b.x} 
              y2={b.y} 
              stroke="currentColor" 
              className={hot ? "text-emerald-300" : "text-white/30"} 
              strokeWidth={hot ? 2 : 1.5} 
              markerEnd="url(#arr)"
            />
          );
        })}

        <defs>
          <marker 
            id="arr" 
            markerWidth="8" 
            markerHeight="8" 
            refX="6" 
            refY="3" 
            orient="auto"
          >
            <path 
              d="M0,0 L0,6 L6,3 z" 
              fill="currentColor" 
              className="text-white/30"
            />
          </marker>
        </defs>

        {/* Nodes */}
        {g.nodes.map(n => {
          const f = focus === n.id;
          const h = hi.includes(n.id);
          return (
            <g 
              key={n.id} 
              transform={`translate(${n.x - 36}, ${n.y - 18})`} 
              onClick={() => onSelect?.(n.id)} 
              style={{ cursor: 'pointer' }}
            >
              <rect 
                width="140" 
                height="32" 
                rx="8" 
                stroke="currentColor" 
                strokeWidth={f || h ? 2 : 1} 
                className={`fill-white/10 ${f || h ? 'text-emerald-300' : 'text-white/20'}`}
              />
              <text 
                x="10" 
                y="20" 
                className="fill-white text-xs"
              >
                {n.label}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="absolute left-3 top-3 flex items-center gap-2 text-xs text-white/70">
        <GitBranch size={14} />
        Architecture
      </div>

      {Object.entries(lanes).map(([k, { l }], i) => (
        <div 
          key={k} 
          className="pointer-events-none absolute left-3 flex items-center gap-1 text-xs text-white/60" 
          style={{ top: [60, 150, 240, 330][i] }}
        >
          {l}
        </div>
      ))}
    </div>
  );
}
