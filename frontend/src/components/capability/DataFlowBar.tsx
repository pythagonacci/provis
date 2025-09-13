import React from 'react';
import { Badge } from '@/components/shared/ui';
import { Capability } from '@/types/capability';

type DataFlowBarProps = {
  capability: Capability | null;
};

export function DataFlowBar({ capability }: DataFlowBarProps) {
  if (!capability) {
    return (
      <div className="mb-3 rounded-xl border border-white/10 bg-white/5 p-2 text-xs text-white/80">
        <div className="flex flex-wrap items-center gap-2">
          <Badge>Waiting for capability data...</Badge>
        </div>
      </div>
    );
  }

  return (
    <div className="mb-3 rounded-xl border border-white/10 bg-white/5 p-2 text-xs text-white/80">
      <div className="flex flex-wrap items-center gap-2">
        <Badge>Entry: {capability.entryPoints.map(f => f.split('/').pop()).join(', ')}</Badge>
        <Badge>Data in: {capability.dataIn.join(', ') || '—'}</Badge>
        <Badge>Data out: {capability.dataOut.join(', ') || '—'}</Badge>
        <Badge>Sources: {capability.sources.map(f => f.split('/').pop()).join(', ') || '—'}</Badge>
        <Badge>Sinks: {capability.sinks.map(s => (s.includes('/') ? s.split('/').pop() : s)).join(', ') || '—'}</Badge>
      </div>
    </div>
  );
}
