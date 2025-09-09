import { FileIcon } from 'lucide-react';
import { Badge } from '@/components/shared/ui';
import type { Capability, DataItem, Policy } from '@/types/capability';

type Props = {
  nodePath: string;
  capability: Capability;
  onDataSelect: (data: DataItem) => void;
};

export function NodeInspector({ nodePath, capability, onDataSelect }: Props) {
  // Find node-related data
  const isEntrypoint = capability.entrypoints.some(e => e.path === nodePath);
  const outgoingEdges = capability.control_flow.filter(e => e.from === nodePath);
  const incomingEdges = capability.control_flow.filter(e => e.to === nodePath);
  
  const role = isEntrypoint ? 'entrypoint' : (outgoingEdges.length ? 'handler' : 'sink');

  // Find related data items
  const relatedSchemas = capability.data_flow.inputs.filter(
    i => i.type?.toLowerCase().includes('schema')
  );
  const relatedEnvs = capability.data_flow.inputs.filter(
    i => i.type?.toLowerCase() === 'env'
  );

  // Find applied policies
  const policies = capability.policies.filter(
    p => p.appliedAt?.startsWith(nodePath) || p.path === nodePath
  );

  // Find related data stores/externals
  const relatedData = [
    ...capability.data_flow.stores.filter(s => s.path?.includes(nodePath)),
    ...capability.data_flow.externals.filter(x => x.client?.includes(nodePath))
  ];

  const shortPath = (p: string) => p.split('/').slice(-2).join('/');

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-white/90">
      <div className="mb-1 flex items-center gap-2 text-sm font-medium">
        <FileIcon size={16} className="text-white/70" /> {nodePath}
      </div>
      
      <p className="mb-2 text-xs text-white/70">
        {capability.summaries.file[nodePath]}
      </p>

      <div className="space-y-3">
        {/* Role & Stats */}
        <div className="flex flex-wrap items-center gap-2">
          <Badge>{role}</Badge>
          {incomingEdges.length > 0 && (
            <Badge>in: {incomingEdges.length}</Badge>
          )}
          {outgoingEdges.length > 0 && (
            <Badge>out: {outgoingEdges.length}</Badge>
          )}
        </div>

        {/* Schemas & Env */}
        {(relatedSchemas.length > 0 || relatedEnvs.length > 0) && (
          <div>
            <div className="text-sm text-slate-300">Inputs</div>
            <div className="mt-1 flex flex-wrap gap-2">
              {relatedSchemas.map((s, i) => (
                <Badge key={i} onClick={() => onDataSelect(s)}>
                  schema: {s.name}
                </Badge>
              ))}
              {relatedEnvs.map((e, i) => (
                <Badge key={i}>env: {e.key}</Badge>
              ))}
            </div>
          </div>
        )}

        {/* Policies */}
        {policies.length > 0 && (
          <div>
            <div className="text-sm text-slate-300">Applied Policies</div>
            <div className="mt-1 flex flex-wrap gap-2">
              {policies.map((p, i) => (
                <Badge key={i}>
                  {p.name}
                  {p.appliedAt && (
                    <span className="ml-1 opacity-60">
                      @ {p.appliedAt.split(':')[1]}
                    </span>
                  )}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Related Data */}
        {relatedData.length > 0 && (
          <div>
            <div className="text-sm text-slate-300">Related Data</div>
            <div className="mt-1 flex flex-wrap gap-2">
              {relatedData.map((d, i) => (
                <Badge 
                  key={i}
                  onClick={() => onDataSelect(d)}
                >
                  {d.type}: {d.name || d.client?.split('/').pop()}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Next Calls */}
        {outgoingEdges.length > 0 && (
          <div>
            <div className="text-sm text-slate-300">Next Calls</div>
            <div className="mt-1 grid gap-1">
              {outgoingEdges.map((e, i) => (
                <div 
                  key={i}
                  className="rounded-lg border border-slate-800 bg-slate-950/60 p-2 text-xs font-mono"
                >
                  {shortPath(e.to)} ({e.kind})
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
