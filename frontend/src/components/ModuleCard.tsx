'use client';

import { File as FileIcon } from 'lucide-react';
import { Badge } from './shared/Badge';

interface Module {
  id: string;
  path: string;
  purpose: string;
  exports: string[];
  imports: string[];
  functions: any[];
  layer: "ui" | "api" | "service" | "data" | "shared";
}

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

interface ModuleCardProps {
  m: Module;
  cap: Capability | null;
  nov: boolean;
}


export default function ModuleCard({ m, cap, nov }: ModuleCardProps) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-white/90">
      <div className="mb-1 flex items-center gap-2 text-sm font-medium">
        <FileIcon size={16} className="text-white/70" />
        {m.path}
      </div>
      <p className="mb-2 text-xs text-white/70">{m.purpose}</p>
      <div className="flex flex-wrap items-center gap-2">
        {m.exports.length > 0 && <Badge>exports: {m.exports.join(', ')}</Badge>}
        {m.functions.length > 0 && <Badge>funcs: {m.functions.length}</Badge>}
        {m.imports.length > 0 && <Badge>imports: {m.imports.length}</Badge>}
        <Badge>{m.layer}</Badge>
        {cap && cap.entryPoints.includes(m.path) && <Badge>Entry</Badge>}
        {cap && cap.orchestrators.some(o => o.split('#')[0] === m.path) && <Badge>Orchestrator</Badge>}
        {cap && cap.sources.includes(m.path) && <Badge>Source</Badge>}
        {cap && cap.sinks.includes(m.path) && <Badge>Sink</Badge>}
        {cap && cap.keyFiles.includes(m.path) && <Badge>Key</Badge>}
      </div>
      {nov && (
        <div className="mt-2 rounded-xl bg-white/5 p-2 text-xs text-white/80">
          <span className="font-medium">In plain English:</span> {m.purpose}
        </div>
      )}
    </div>
  );
}
