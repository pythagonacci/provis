'use client';

interface ChipProps {
  children: React.ReactNode;
}

export const Chip = ({ children }: ChipProps) => (
  <span className="inline-flex items-center rounded-md bg-white/10 px-2 py-0.5 text-xs text-white/80">
    {children}
  </span>
);

export default Chip;
