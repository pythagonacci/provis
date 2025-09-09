import { Badge } from '@/components/shared/ui';
import type { Capability } from '@/types/capability';

type Props = {
  capability: Capability;
};

export function DataFlowBar({ capability }: Props) {
  const { data_flow: flow, entrypoints } = capability;

  const formatItems = (items: any[]) => 
    items.map(i => i.name || i.key || i.path?.split('/').pop()).filter(Boolean).join(', ') || '—';

  return (
    <div className="mb-3 rounded-xl border border-white/10 bg-white/5 p-2 text-xs text-white/80">
      <div className="flex flex-wrap items-center gap-2">
        <Badge>
          Entry: {entrypoints.map(e => e.path.split('/').pop()).join(', ')}
        </Badge>
        <Badge>
          Data in: {formatItems(flow.inputs)}
        </Badge>
        <Badge>
          Data out: {formatItems(flow.stores)}
        </Badge>
        <Badge>
          Sources: {formatItems(flow.inputs)}
        </Badge>
        <Badge>
          Sinks: {formatItems(flow.externals)}
        </Badge>
      </div>
    </div>
  );
}
