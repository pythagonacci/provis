'use client';

import { ArrowRight } from 'lucide-react';

interface DataItemExplanationProps {
  title: string;
  items: string[];
  color: 'green' | 'blue' | 'purple' | 'orange';
}

export default function DataItemExplanation({ title, items, color }: DataItemExplanationProps) {
  const colorClasses = {
    green: {
      bg: 'bg-green-50',
      border: 'border-green-200',
      text: 'text-green-900',
      subtext: 'text-green-700',
      dot: 'bg-green-500'
    },
    blue: {
      bg: 'bg-blue-50',
      border: 'border-blue-200',
      text: 'text-blue-900',
      subtext: 'text-blue-700',
      dot: 'bg-blue-500'
    },
    purple: {
      bg: 'bg-purple-50',
      border: 'border-purple-200',
      text: 'text-purple-900',
      subtext: 'text-purple-700',
      dot: 'bg-purple-500'
    },
    orange: {
      bg: 'bg-orange-50',
      border: 'border-orange-200',
      text: 'text-orange-900',
      subtext: 'text-orange-700',
      dot: 'bg-orange-500'
    }
  };

  const classes = colorClasses[color];

  return (
    <div className={`rounded-lg border p-4 ${classes.bg} ${classes.border}`}>
      <div className="flex items-center justify-between mb-3">
        <h4 className={`font-medium ${classes.text}`}>{title}</h4>
        <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${classes.bg} ${classes.text}`}>
          {items.length} items
        </span>
      </div>
      
      <div className="space-y-2">
        {items.length > 0 ? (
          items.map((item, index) => (
            <div key={index} className="flex items-center">
              <div className={`w-2 h-2 rounded-full mr-3 ${classes.dot}`}></div>
              <span className={`text-sm ${classes.subtext}`}>{item}</span>
            </div>
          ))
        ) : (
          <div className={`text-sm ${classes.subtext} italic`}>No {title.toLowerCase()} defined</div>
        )}
      </div>
      
      {items.length > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-200">
          <div className="flex items-center text-xs text-gray-500">
            <span>Data flows through these {title.toLowerCase()}</span>
            <ArrowRight className="w-3 h-3 mx-1" />
            <span>Processed by application logic</span>
          </div>
        </div>
      )}
    </div>
  );
}
