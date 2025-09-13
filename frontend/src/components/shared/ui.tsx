import React from 'react';

export function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full border border-white/15 bg-white/5 px-2.5 py-0.5 text-xs text-white/80 backdrop-blur">
      {children}
    </span>
  );
}

export function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-md bg-white/10 px-2 py-0.5 text-xs text-white/80">
      {children}
    </span>
  );
}

export function SectionTitle({ icon: Icon, title }: { icon: any; title: string }) {
  return (
    <div className="flex items-center gap-2 text-white/90">
      <Icon size={16} className="opacity-80" />
      <h3 className="text-sm font-medium tracking-wide">{title}</h3>
    </div>
  );
}
