import { ListTree } from 'lucide-react';
import { SectionTitle } from '@/components/shared/ui';
import type { NarrativeStep } from '@/types/capability';

type Props = {
  steps: NarrativeStep[];
  onHover?: (fileId?: string) => void;
  onSelect?: (fileId?: string) => void;
};

export function NarrativeSteps({ steps, onHover, onSelect }: Props) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-white/90">
      <SectionTitle icon={ListTree} title="Narrated steps" />
      
      <ol className="mt-2 space-y-2 text-sm">
        {steps.map((step, i) => (
          <li 
            key={i}
            className="flex cursor-pointer items-start gap-2 rounded-lg p-1 hover:bg-white/5"
            onMouseEnter={() => onHover?.(step.fileId)}
            onMouseLeave={() => onHover?.(undefined)}
            onClick={() => onSelect?.(step.fileId)}
          >
            <span className="mt-0.5 inline-flex h-5 w-5 items-center justify-center rounded-full bg-white/10 text-xs text-white/80">
              {i + 1}
            </span>
            
            <div>
              <div className="font-medium">{step.label}</div>
              {step.detail && (
                <div className="text-white/70">{step.detail}</div>
              )}
              {step.scenario && step.scenario !== 'happy' && (
                <div className="mt-1 text-xs">
                  <span className={`rounded-full px-2 py-0.5 ${
                    step.scenario === 'error' 
                      ? 'bg-red-900/20 text-red-200' 
                      : 'bg-amber-900/20 text-amber-200'
                  }`}>
                    {step.scenario}
                  </span>
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
