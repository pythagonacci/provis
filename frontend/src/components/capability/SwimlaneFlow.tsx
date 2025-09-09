import { useMemo } from 'react';
import type { ControlFlowEdge } from '@/types/capability';

type Props = {
  edges: ControlFlowEdge[];
  swimlanes: {
    web: string[];
    api: string[];
    workers: string[];
  };
  onSelect: (node: string) => void;
  selected?: string | null;
};

export function SwimlaneFlow({ edges, swimlanes, onSelect, selected }: Props) {
  // Get unique nodes from edges
  const nodes = useMemo(() => 
    Array.from(new Set(edges.flatMap(e => [e.from, e.to]))),
    [edges]
  );

  // Determine lane for each node
  const laneFor = (node: string) => 
    Object.entries(swimlanes).find(([,list]) => list.includes(node))?.[0] || 'other';

  const lanes = ['web', 'api', 'workers'];
  const cols = nodes.map(n => ({ n, lane: laneFor(n) }));
  const laneIndex = (lane: string) => Math.max(0, lanes.indexOf(lane));

  const width = Math.max(900, nodes.length * 240);
  const laneHeight = 110;

  return (
    <div className="bg-slate-950/60 border border-slate-800 rounded-2xl p-4">
      <div className="text-slate-300 text-sm mb-2">
        Flow (swimlanes: web / api / workers). Click a node to explain.
      </div>
      <div className="overflow-x-auto">
        <svg 
          width={width} 
          height={(lanes.length + 1) * laneHeight + 40}
          className="min-w-[900px]"
        >
          {/* Lane backgrounds */}
          {lanes.map((lane, i) => (
            <g key={lane} transform={`translate(0, ${20 + i * laneHeight})`}>
              <rect 
                x={0} 
                y={0} 
                width={width} 
                height={laneHeight} 
                className="fill-slate-900"
              />
              <text 
                x={10} 
                y={18} 
                className="fill-slate-500 text-[12px]"
              >
                {lane.toUpperCase()}
              </text>
            </g>
          ))}

          {/* Nodes */}
          {cols.map(({n, lane}, idx) => {
            const x = 40 + idx * 220;
            const y = 20 + laneIndex(lane) * laneHeight + 30;
            const isSel = selected === n;
            
            return (
              <g key={n} transform={`translate(${x}, ${y})`}>
                <rect 
                  rx={12} 
                  ry={12} 
                  width={200} 
                  height={60}
                  className={`stroke-2 cursor-pointer ${
                    isSel 
                      ? 'fill-emerald-900/30 stroke-emerald-500' 
                      : 'fill-slate-800 stroke-slate-700 hover:stroke-slate-500'
                  }`}
                  onClick={() => onSelect(n)}
                />
                <text 
                  x={12} 
                  y={35} 
                  className="fill-slate-200 text-[12px] font-mono"
                >
                  {n.split('/').slice(-2).join('/')}
                </text>
              </g>
            );
          })}

          {/* Edges */}
          {edges.map((e, idx) => {
            const fromIdx = nodes.indexOf(e.from);
            const toIdx = nodes.indexOf(e.to);
            if (fromIdx < 0 || toIdx < 0) return null;

            const x1 = 40 + fromIdx * 220 + 200;
            const y1 = 20 + laneIndex(laneFor(e.from)) * laneHeight + 60;
            const x2 = 40 + toIdx * 220;
            const y2 = 20 + laneIndex(laneFor(e.to)) * laneHeight + 60;

            return (
              <g key={idx}>
                <line 
                  x1={x1} 
                  y1={y1} 
                  x2={x2} 
                  y2={y2}
                  className="stroke-slate-600"
                  strokeWidth={2}
                  markerEnd="url(#arrow)"
                />
              </g>
            );
          })}

          {/* Arrow marker definition */}
          <defs>
            <marker 
              id="arrow" 
              markerWidth="10" 
              markerHeight="10" 
              refX="6" 
              refY="3" 
              orient="auto" 
              markerUnits="strokeWidth"
            >
              <path 
                d="M0,0 L0,6 L9,3 z" 
                className="fill-slate-600" 
              />
            </marker>
          </defs>
        </svg>
      </div>
    </div>
  );
}
