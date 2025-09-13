import React from 'react';
import { ListTree } from 'lucide-react';
import { SectionTitle } from '@/components/shared/ui';

type NarrativeStepsProps = {
  steps: { title: string; description: string; fileId?: string }[];
  onHover?: (fileId?: string) => void;
  onSelect?: (fileId?: string) => void;
};

export function NarrativeSteps({ steps, onHover, onSelect }: NarrativeStepsProps) {
  if (steps.length === 0) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-white/90">
        <SectionTitle icon={ListTree} title="Narrated steps" />
        <div className="mt-2 text-xs text-white/70">
          No steps available - waiting for capability data
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-white/90">
      <SectionTitle icon={ListTree} title="Narrated steps" />
      <ol className="mt-2 space-y-2 text-sm">
        {steps.map((s, i) => (
          <li 
            key={i} 
            className="flex cursor-pointer items-start gap-2 rounded-lg p-1 hover:bg-white/5" 
            onMouseEnter={() => onHover?.(s.fileId)} 
            onMouseLeave={() => onHover?.(undefined)} 
            onClick={() => onSelect?.(s.fileId)}
          >
            <span className="mt-0.5 inline-flex h-5 w-5 items-center justify-center rounded-full bg-white/10 text-xs text-white/80">
              {i + 1}
            </span>
            <div>
              <div className="font-medium">{s.title}</div>
              <div className="text-white/70">{s.description}</div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
