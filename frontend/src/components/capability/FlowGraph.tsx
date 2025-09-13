'use client';

interface FlowGraphProps {
  dataFlow: {
    inputs: Array<any>;
    outputs: Array<any>;
    stores: Array<any>;
    externals: Array<any>;
  };
  controlFlow: Array<{ from: string; to: string; type: string }>;
  nodeIndex: Record<string, any>;
}

export default function FlowGraph({ dataFlow, controlFlow, nodeIndex }: FlowGraphProps) {
  return (
    <div className="space-y-6">
      {/* Simple Flow Visualization */}
      <div className="bg-gray-50 rounded-lg p-6">
        <h3 className="text-sm font-medium text-gray-900 mb-4">Data & Control Flow</h3>
        
        {/* Data Flow */}
        <div className="mb-6">
          <h4 className="text-xs font-medium text-gray-700 mb-3">Data Flow</h4>
          <div className="flex flex-wrap items-center gap-2">
            {dataFlow.inputs.slice(0, 3).map((input, index) => (
              <div key={`input-${index}`} className="bg-green-100 text-green-800 px-2 py-1 rounded text-xs">
                {input.name}
              </div>
            ))}
            <div className="text-gray-400">→</div>
            {dataFlow.stores.slice(0, 2).map((store, index) => (
              <div key={`store-${index}`} className="bg-blue-100 text-blue-800 px-2 py-1 rounded text-xs">
                {store.name}
              </div>
            ))}
            <div className="text-gray-400">→</div>
            {dataFlow.outputs.slice(0, 3).map((output, index) => (
              <div key={`output-${index}`} className="bg-purple-100 text-purple-800 px-2 py-1 rounded text-xs">
                {output.name}
              </div>
            ))}
          </div>
        </div>

        {/* Control Flow */}
        <div>
          <h4 className="text-xs font-medium text-gray-700 mb-3">Control Flow</h4>
          <div className="space-y-2">
            {controlFlow.slice(0, 5).map((flow, index) => (
              <div key={index} className="flex items-center text-xs">
                <div className="bg-gray-100 text-gray-700 px-2 py-1 rounded truncate max-w-32">
                  {flow.from}
                </div>
                <div className="mx-2 text-gray-400">→</div>
                <div className="bg-gray-100 text-gray-700 px-2 py-1 rounded truncate max-w-32">
                  {flow.to}
                </div>
                <div className="ml-2 text-gray-500">({flow.type})</div>
              </div>
            ))}
            {controlFlow.length > 5 && (
              <div className="text-xs text-gray-500 italic">
                +{controlFlow.length - 5} more connections
              </div>
            )}
          </div>
        </div>
      </div>

      {/* External Services */}
      <div>
        <h4 className="text-sm font-medium text-gray-900 mb-3">External Dependencies</h4>
        <div className="flex flex-wrap gap-2">
          {dataFlow.externals.map((external, index) => (
            <div key={index} className="bg-orange-100 text-orange-800 px-3 py-1 rounded-full text-sm">
              {external.name}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
