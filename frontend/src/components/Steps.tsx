'use client';

import { ListTree } from 'lucide-react';
import { Title } from './shared/Title';

interface StepsProps {
  steps: {
    title: string;
    description: string;
    fileId?: string;
  }[];
  onHover?: (id?: string) => void;
  onSelect?: (id?: string) => void;
}


export default function Steps({ steps, onHover, onSelect }: StepsProps) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-white/90">
      <Title icon={ListTree} title="Steps" />
      <ol className="mt-2 space-y-2 text-sm">
        {steps.map((s, i) => (
          <li 
            key={i} 
            className="flex cursor-pointer items-start gap-2 rounded-lg p-1 hover:bg-white/5" 
            onMouseEnter={() => onHover?.(s.fileId)} 
            onMouseLeave={() => onHover?.()} 
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
