import React from 'react';
import { FileIcon } from 'lucide-react';
import { Badge } from '@/components/shared/ui';
import { FileNode, Capability } from '@/types/capability';

type NodeInspectorProps = {
  file: FileNode | null;
  selectedCapability: Capability | null;
  novice: boolean;
};

export function NodeInspector({ file, selectedCapability, novice }: NodeInspectorProps) {
  if (!file) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-center text-white/70">
        Select a file from the folder map to see details.
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-white/90">
      <div className="mb-1 flex items-center gap-2 text-sm font-medium">
        <FileIcon size={16} className="text-white/70" /> {file.path}
      </div>
      <p className="mb-2 text-xs text-white/70">{file.purpose}</p>
      <div className="flex flex-wrap items-center gap-2">
        {file.exports.length > 0 && <Badge>exports: {file.exports.join(", ")}</Badge>}
        {file.functions.length > 0 && <Badge>funcs: {file.functions.length}</Badge>}
        {file.imports.length > 0 && <Badge>imports: {file.imports.length}</Badge>}
        {/* role badges based on selected capability */}
        {selectedCapability && selectedCapability.entryPoints.includes(file.path) && <Badge>Entry point</Badge>}
        {selectedCapability && selectedCapability.orchestrators.some(o => o.split('#')[0] === file.path) && <Badge>Orchestrator</Badge>}
        {selectedCapability && selectedCapability.sources.includes(file.path) && <Badge>Source</Badge>}
        {selectedCapability && selectedCapability.sinks.includes(file.path) && <Badge>Sink</Badge>}
        {selectedCapability && selectedCapability.keyFiles.includes(file.path) && <Badge>Key file</Badge>}
      </div>
      {novice && (
        <div className="mt-2 rounded-xl bg-white/5 p-2 text-xs text-white/80">
          <span className="font-medium">In plain English:</span> {file.purpose}
        </div>
      )}
    </div>
  );
}
