'use client';

interface SwimlaneFlowProps {
  swimlanes: Record<string, string[]>;
  nodeIndex: Record<string, any>;
  controlFlow: Array<{ from: string; to: string; type: string }>;
  steps: Array<{ title: string; description: string; fileId?: string }>;
}

export default function SwimlaneFlow({ swimlanes, nodeIndex, controlFlow, steps }: SwimlaneFlowProps) {
  const laneColors = {
    api: 'bg-blue-100 border-blue-300 text-blue-800',
    web: 'bg-green-100 border-green-300 text-green-800',
    workers: 'bg-purple-100 border-purple-300 text-purple-800',
    other: 'bg-gray-100 border-gray-300 text-gray-800'
  };

  return (
    <div className="space-y-6">
      {/* Steps Flow */}
      <div>
        <h3 className="text-sm font-medium text-gray-900 mb-3">Processing Steps</h3>
        <div className="flex flex-wrap gap-2">
          {steps.map((step, index) => (
            <div key={index} className="flex items-center">
              <div className="bg-blue-50 border border-blue-200 rounded-lg px-3 py-2">
                <div className="flex items-center">
                  <div className="w-6 h-6 bg-blue-600 text-white rounded-full flex items-center justify-center text-xs font-medium mr-2">
                    {index + 1}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-blue-900">{step.title}</p>
                    <p className="text-xs text-blue-700">{step.description}</p>
                  </div>
                </div>
              </div>
              {index < steps.length - 1 && (
                <div className="mx-2 text-gray-400">→</div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Swimlanes */}
      <div>
        <h3 className="text-sm font-medium text-gray-900 mb-3">File Organization</h3>
        <div className="space-y-4">
          {Object.entries(swimlanes).map(([lane, files]) => (
            <div key={lane} className="border border-gray-200 rounded-lg overflow-hidden">
              <div className={`px-4 py-2 ${laneColors[lane as keyof typeof laneColors] || laneColors.other}`}>
                <h4 className="font-medium capitalize">{lane} ({files.length})</h4>
              </div>
              <div className="p-4">
                {files.length > 0 ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                    {files.slice(0, 12).map((file, index) => (
                      <div key={index} className="text-sm text-gray-700 bg-gray-50 rounded px-2 py-1 truncate">
                        {file}
                      </div>
                    ))}
                    {files.length > 12 && (
                      <div className="text-sm text-gray-500 italic">
                        +{files.length - 12} more files
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500 italic">No files in this lane</p>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}