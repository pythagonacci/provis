'use client';

import { Database } from 'lucide-react';
import { Title } from './shared/Title';
import { Chip } from './shared/Chip';

interface Model {
  id: string;
  engine: "prisma" | "mongoose" | "sequelize" | "sql" | "zod" | "custom";
  file: string;
  fields: {
    name: string;
    type: string;
    optional?: boolean;
    relation?: string;
  }[];
}

interface ModelsProps {
  models: Model[];
  onSelect?: (id: string) => void;
}


export default function Models({ models, onSelect }: ModelsProps) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-white/90">
      <Title icon={Database} title="Models" />
      <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
        {models.map(m => (
          <div key={m.id} className="rounded-xl bg-white/5 p-2 text-xs">
            <div className="mb-1 flex items-center justify-between">
              <div className="font-medium">{m.id}</div>
              <Chip>{m.engine}</Chip>
            </div>
            <div className="mb-1 text-white/70">
              in <button 
                className="underline decoration-white/20 underline-offset-4 hover:text-white" 
                onClick={() => onSelect?.(m.file)}
              >
                {m.file}
              </button>
            </div>
            <ul className="grid grid-cols-2 gap-x-4 text-white/70">
              {m.fields.map(f => (
                <li key={f.name}>
                  <span className="text-white/90">{f.name}</span>: {f.type}{f.optional ? "?" : ""}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
