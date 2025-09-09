import { useState } from 'react';
import { Bug, Server, GitCommitVertical, Repeat } from 'lucide-react';
import { Badge, Chip, Section } from '@/components/shared/ui';
import { SwimlaneFlow } from './SwimlaneFlow';
import { DataFlowBar } from './DataFlowBar';
import { NodeInspector } from './NodeInspector';
import { NarrativeSteps } from './NarrativeSteps';
import { PoliciesAndContracts } from './PoliciesAndContracts';
import type { Capability, DataItem } from '@/types/capability';

type Props = {
  capability: Capability;
};

export function CapabilityView({ capability }: Props) {
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [highlightedNode, setHighlightedNode] = useState<string | null>(null);
  const [selectedData, setSelectedData] = useState<DataItem | null>(null);
  const [scenario, setScenario] = useState<'happy' | 'edge' | 'error'>('happy');

  // Helper to determine status tone
  const statusTone = (s: string) => 
    s === 'healthy' ? 'good' : s === 'degraded' ? 'warn' : 'bad';

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-950 to-slate-900 text-slate-100">
      <div className="max-w-[1500px] mx-auto p-4 md:p-6 lg:p-8">
        {/* Header */}
        <header className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">
              {capability.title}
            </h1>
            <p className="text-slate-400 text-sm">
              End-to-end capability flow
            </p>
          </div>
          
          <div className="flex items-center gap-2">
            <Chip>
              <Bug className="w-3 h-3"/> {capability.status}
            </Chip>
            <Chip>
              <GitCommitVertical className="w-3 h-3"/> Recent changes
            </Chip>
            <Chip>
              <Repeat className="w-3 h-3"/>
              <select 
                className="bg-transparent ml-1 outline-none"
                value={scenario}
                onChange={e => setScenario(e.target.value as any)}
              >
                <option value="happy">Happy path</option>
                <option value="edge">Edge case</option>
                <option value="error">Error case</option>
              </select>
            </Chip>
          </div>
        </header>

        {/* Entrypoints */}
        <Section title={<span className="flex items-center gap-2"><Server className="w-4 h-4"/> Entrypoints</span>}>
          <div className="flex flex-wrap gap-2">
            {capability.entrypoints.map((e, i) => (
              <Chip key={i}>
                {e.path} 
                <span className="opacity-60 ml-1">
                  ({e.framework}/{e.kind})
                </span>
              </Chip>
            ))}
          </div>
        </Section>

        {/* Flow Visualization */}
        <div className="space-y-4">
          <DataFlowBar capability={capability} />
          
          <SwimlaneFlow 
            edges={capability.control_flow}
            swimlanes={capability.swimlanes}
            onSelect={setSelectedNode}
            selected={selectedNode}
          />
        </div>

        {/* Details Grid */}
        <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            {/* Node Inspector */}
            {selectedNode && (
              <NodeInspector
                nodePath={selectedNode}
                capability={capability}
                onDataSelect={setSelectedData}
              />
            )}

            {/* Narrative Steps */}
            <NarrativeSteps
              steps={capability.summaries.narrative}
              onHover={setHighlightedNode}
              onSelect={setSelectedNode}
            />
          </div>

          <div>
            <PoliciesAndContracts
              policies={capability.policies}
              contracts={capability.contracts}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
