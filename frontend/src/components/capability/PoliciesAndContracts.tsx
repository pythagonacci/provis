import { Shield, FileCode2 } from 'lucide-react';
import { Section } from '@/components/shared/ui';
import type { Policy, Contract } from '@/types/capability';

type Props = {
  policies: Policy[];
  contracts: Contract[];
};

export function PoliciesAndContracts({ policies, contracts }: Props) {
  return (
    <Section title={<span className="flex items-center gap-2"><Shield className="w-4 h-4"/> Policies & Contracts</span>}>
      <div className="space-y-4">
        {/* Policies */}
        <div>
          <div className="text-slate-300 text-sm mb-1">Policies</div>
          <ul className="space-y-2">
            {policies.map((p, idx) => (
              <li key={idx} className="p-3 rounded-xl bg-slate-950/50 border border-slate-800 text-sm">
                <div className="flex items-center gap-2">
                  <Shield className="w-3 h-3"/> 
                  {p.name}
                  <span className="text-slate-500 ml-2">
                    {p.appliedAt || p.path}
                  </span>
                </div>
                <div className="mt-1 text-xs text-slate-400">
                  Type: {p.type}
                </div>
              </li>
            ))}
            {policies.length === 0 && (
              <div className="text-slate-500 text-sm">
                No explicit policies detected.
              </div>
            )}
          </ul>
        </div>

        {/* Contracts */}
        <div>
          <div className="text-slate-300 text-sm mb-1">Contracts</div>
          <ul className="space-y-2">
            {contracts.map((c, idx) => (
              <li key={idx} className="p-3 rounded-xl bg-slate-950/50 border border-slate-800 text-sm">
                <div className="flex items-center gap-2">
                  <FileCode2 className="w-3 h-3"/> 
                  {c.name} 
                  <span className="text-slate-500">({c.kind})</span>
                </div>
                <div className="font-mono text-slate-300 mt-1">{c.path}</div>
                {c.fields && (
                  <div className="text-xs text-slate-500">
                    fields: {c.fields.join(", ")}
                  </div>
                )}
              </li>
            ))}
            {contracts.length === 0 && (
              <div className="text-slate-500 text-sm">
                No contracts indexed.
              </div>
            )}
          </ul>
        </div>
      </div>
    </Section>
  );
}
