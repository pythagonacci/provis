'use client';

interface TitleProps {
  icon: any;
  title: string;
}

export const Title = ({ icon: Icon, title }: TitleProps) => (
  <div className="flex items-center gap-2 text-white/90">
    <Icon size={16} className="opacity-80" />
    <h3 className="text-sm font-medium tracking-wide">{title}</h3>
  </div>
);

export default Title;
