import { ReactNode } from 'react';

export function Badge({ 
  children, 
  tone = 'default' 
}: { 
  children: ReactNode; 
  tone?: 'default' | 'good' | 'warn' | 'bad';
}) {
  const toneStyles = {
    default: 'bg-slate-800 text-slate-100 border-slate-700',
    good: 'bg-emerald-900/40 text-emerald-200 border-emerald-700/60',
    warn: 'bg-amber-900/40 text-amber-200 border-amber-700/60',
    bad: 'bg-red-900/40 text-red-200 border-red-700/60',
  };

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-2xl text-xs border ${toneStyles[tone]}`}>
      {children}
    </span>
  );
}

export function Chip({ 
  children, 
  onClick 
}: { 
  children: ReactNode;
  onClick?: () => void;
}) {
  return (
    <span 
      className={`inline-flex items-center rounded-md bg-white/10 px-2 py-0.5 text-xs text-white/80 ${onClick ? 'cursor-pointer hover:bg-white/15' : ''}`}
      onClick={onClick}
    >
      {children}
    </span>
  );
}

export function Section({ 
  title, 
  children, 
  right 
}: { 
  title: ReactNode;
  children: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 mb-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 text-slate-200 font-medium">{title}</div>
        {right && <div>{right}</div>}
      </div>
      {children}
    </div>
  );
}

export function SectionTitle({ 
  icon: Icon, 
  title 
}: { 
  icon: any; 
  title: string;
}) {
  return (
    <div className="flex items-center gap-2 text-white/90">
      <Icon size={16} className="opacity-80" />
      <h3 className="text-sm font-medium tracking-wide">{title}</h3>
    </div>
  );
}
