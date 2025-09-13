'use client';

interface DataFlowBarProps {
  dataFlow: {
    inputs: Array<{
      type: string;
      name: string;
      path?: string;
      fields?: Array<{ name: string; type: string }>;
    }>;
    outputs: Array<{
      type: string;
      name: string;
      path?: string;
      mime?: string;
    }>;
    stores: Array<{
      type: string;
      name: string;
      path?: string;
      fields?: Array<{ name: string; type: string }>;
    }>;
    externals: Array<{
      name: string;
      type: string;
    }>;
  };
  sources: string[];
  sinks: string[];
}

export default function DataFlowBar({ dataFlow, sources, sinks }: DataFlowBarProps) {
  return (
    <div className="space-y-6">
      {/* Data Flow Overview */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Inputs */}
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <h4 className="font-medium text-green-900 mb-2">Inputs ({dataFlow.inputs.length})</h4>
          <div className="space-y-1">
            {dataFlow.inputs.slice(0, 3).map((input, index) => (
              <div key={index} className="text-sm text-green-700">
                {input.name}
              </div>
            ))}
            {dataFlow.inputs.length > 3 && (
              <div className="text-xs text-green-600">+{dataFlow.inputs.length - 3} more</div>
            )}
          </div>
        </div>

        {/* Stores */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <h4 className="font-medium text-blue-900 mb-2">Data Stores ({dataFlow.stores.length})</h4>
          <div className="space-y-1">
            {dataFlow.stores.slice(0, 3).map((store, index) => (
              <div key={index} className="text-sm text-blue-700">
                {store.name}
              </div>
            ))}
            {dataFlow.stores.length > 3 && (
              <div className="text-xs text-blue-600">+{dataFlow.stores.length - 3} more</div>
            )}
          </div>
        </div>

        {/* Outputs */}
        <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
          <h4 className="font-medium text-purple-900 mb-2">Outputs ({dataFlow.outputs.length})</h4>
          <div className="space-y-1">
            {dataFlow.outputs.slice(0, 3).map((output, index) => (
              <div key={index} className="text-sm text-purple-700">
                {output.name}
              </div>
            ))}
            {dataFlow.outputs.length > 3 && (
              <div className="text-xs text-purple-600">+{dataFlow.outputs.length - 3} more</div>
            )}
          </div>
        </div>

        {/* Externals */}
        <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
          <h4 className="font-medium text-orange-900 mb-2">External Services ({dataFlow.externals.length})</h4>
          <div className="space-y-1">
            {dataFlow.externals.slice(0, 3).map((external, index) => (
              <div key={index} className="text-sm text-orange-700">
                {external.name}
              </div>
            ))}
            {dataFlow.externals.length > 3 && (
              <div className="text-xs text-orange-600">+{dataFlow.externals.length - 3} more</div>
            )}
          </div>
        </div>
      </div>

      {/* Sources and Sinks */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h4 className="font-medium text-gray-900 mb-3">Data Sources</h4>
          <div className="space-y-2">
            {sources.map((source, index) => (
              <div key={index} className="flex items-center p-3 bg-gray-50 rounded-lg">
                <div className="w-2 h-2 bg-green-500 rounded-full mr-3"></div>
                <span className="text-sm text-gray-700">{source}</span>
              </div>
            ))}
          </div>
        </div>

        <div>
          <h4 className="font-medium text-gray-900 mb-3">Data Sinks</h4>
          <div className="space-y-2">
            {sinks.map((sink, index) => (
              <div key={index} className="flex items-center p-3 bg-gray-50 rounded-lg">
                <div className="w-2 h-2 bg-red-500 rounded-full mr-3"></div>
                <span className="text-sm text-gray-700">{sink}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}