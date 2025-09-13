import React from 'react';
import { Wand2 } from 'lucide-react';
import { SectionTitle, Chip } from '@/components/shared/ui';
import { Suggestion } from '@/types/capability';

type PoliciesAndContractsProps = {
  suggestions: Suggestion[];
  onSelect?: (fileId: string) => void;
};

export function PoliciesAndContracts({ suggestions, onSelect }: PoliciesAndContractsProps) {
  if (suggestions.length === 0) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-white/90">
        <SectionTitle icon={Wand2} title="Edit suggestions" />
        <div className="mt-2 text-xs text-white/70">
          No suggestions available - waiting for analysis data
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-white/90">
      <SectionTitle icon={Wand2} title="Edit suggestions" />
      <ul className="mt-2 space-y-2 text-sm">
        {suggestions.map((it, i) => (
          <li 
            key={i} 
            className="flex cursor-pointer items-start justify-between gap-3 rounded-xl bg-white/5 p-2 hover:bg-white/10" 
            onClick={() => onSelect?.(it.fileId)}
          >
            <div>
              <div className="font-medium">{it.fileId}</div>
              <div className="text-white/70">{it.rationale}</div>
            </div>
            <Chip>{it.confidence}</Chip>
          </li>
        ))}
      </ul>
    </div>
  );
}
