import React from 'react';

interface HeroProps {
  title: string;
  subtitle?: string;
}

export default function Hero({ title, subtitle }: HeroProps) {
  return (
    <div className="hero">
      <h1 className="text-4xl font-bold">{title}</h1>
      {subtitle && <p className="text-xl mt-4">{subtitle}</p>}
    </div>
  );
}
