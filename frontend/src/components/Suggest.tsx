'use client';

import { Wand2 } from 'lucide-react';
import { Title } from './shared/Title';
import { Chip } from './shared/Chip';

interface SuggestProps {
  items: {
    fileId: string;
    rationale: string;
    confidence: "High" | "Med" | "Low";
  }[];
  onSelect?: (id: string) => void;
}


export default function Suggest({ items, onSelect }: SuggestProps) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-white/90">
      <Title icon={Wand2} title="Suggestions" />
      <ul className="mt-2 space-y-2 text-sm">
        {items.map((it, i) => (
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
