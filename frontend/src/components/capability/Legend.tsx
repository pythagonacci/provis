'use client';

export default function Legend() {
  const legendItems = [
    {
      color: 'bg-blue-100 border-blue-300 text-blue-800',
      label: 'API Routes',
      description: 'HTTP endpoints and route handlers'
    },
    {
      color: 'bg-green-100 border-green-300 text-green-800',
      label: 'Web Components',
      description: 'UI components and pages'
    },
    {
      color: 'bg-purple-100 border-purple-300 text-purple-800',
      label: 'Workers',
      description: 'Background tasks and workers'
    },
    {
      color: 'bg-gray-100 border-gray-300 text-gray-800',
      label: 'Other',
      description: 'Utilities and other files'
    }
  ];

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <h3 className="text-sm font-medium text-gray-900 mb-3">Legend</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {legendItems.map((item) => (
          <div key={item.label} className="flex items-center">
            <div className={`w-3 h-3 rounded border mr-2 ${item.color}`}></div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 truncate">{item.label}</p>
              <p className="text-xs text-gray-500 truncate">{item.description}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
