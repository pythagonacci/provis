'use client';

import { Badge } from './shared/Badge';

interface Capability {
  id: string;
  name: string;
  purpose: string;
  entryPoints: string[];
  orchestrators: string[];
  sources: string[];
  sinks: string[];
  dataIn: string[];
  dataOut: string[];
  keyFiles: string[];
  steps: {
    title: string;
    description: string;
    fileId?: string;
  }[];
}

interface DataFlowBarProps {
  cap: Capability | null;
}

export default function DataFlowBar({ cap }: DataFlowBarProps) {
  if (!cap) return null;

  return (
    <div className="mb-3 rounded-xl border border-white/10 bg-white/5 p-2 text-xs text-white/80">
      <div className="flex flex-wrap items-center gap-2">
        <Badge>Entry: {cap.entryPoints.map(f => f.split('/').pop()).join(', ')}</Badge>
        <Badge>In: {cap.dataIn.join(', ') || '—'}</Badge>
        <Badge>Out: {cap.dataOut.join(', ') || '—'}</Badge>
        <Badge>Sources: {cap.sources.map(f => f.split('/').pop()).join(', ') || '—'}</Badge>
        <Badge>Sinks: {cap.sinks.map(s => (s.includes('/') ? s.split('/').pop() : s)).join(', ') || '—'}</Badge>
      </div>
    </div>
  );
}
