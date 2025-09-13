'use client';

import { CheckCircle, AlertTriangle, Shield, FileText, Clock } from 'lucide-react';

interface TestsPanelProps {
  policies: Array<{
    type: string;
    [key: string]: any;
  }>;
  contracts: Array<{
    name: string;
    kind: string;
    path: string;
    fields: Array<{
      name: string;
      type: string;
    }>;
  }>;
  suspectRank: string[];
}

export default function TestsPanel({ policies, contracts, suspectRank }: TestsPanelProps) {
  return (
    <div className="p-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Policies */}
        <div>
          <div className="flex items-center mb-3">
            <Shield className="w-5 h-5 text-blue-600 mr-2" />
            <h4 className="font-medium text-gray-900">Security Policies</h4>
          </div>
          <div className="space-y-2">
            {policies.length > 0 ? (
              policies.map((policy, index) => (
                <div key={index} className="flex items-center p-2 bg-blue-50 rounded">
                  <CheckCircle className="w-4 h-4 text-blue-600 mr-2" />
                  <div>
                    <p className="text-sm font-medium text-blue-900">{policy.type}</p>
                    {policy.type === 'cors' && (
                      <p className="text-xs text-blue-700">Cross-origin resource sharing</p>
                    )}
                    {policy.type === 'rateLimit' && (
                      <p className="text-xs text-blue-700">{policy.requests} requests per {policy.window}</p>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <div className="text-sm text-gray-500 italic">No policies defined</div>
            )}
          </div>
        </div>

        {/* Contracts */}
        <div>
          <div className="flex items-center mb-3">
            <FileText className="w-5 h-5 text-green-600 mr-2" />
            <h4 className="font-medium text-gray-900">API Contracts</h4>
          </div>
          <div className="space-y-2">
            {contracts.length > 0 ? (
              contracts.map((contract, index) => (
                <div key={index} className="flex items-center p-2 bg-green-50 rounded">
                  <CheckCircle className="w-4 h-4 text-green-600 mr-2" />
                  <div>
                    <p className="text-sm font-medium text-green-900">{contract.name}</p>
                    <p className="text-xs text-green-700">{contract.kind}</p>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-sm text-gray-500 italic">No contracts defined</div>
            )}
          </div>
        </div>

        {/* Suspect Files */}
        <div>
          <div className="flex items-center mb-3">
            <AlertTriangle className="w-5 h-5 text-orange-600 mr-2" />
            <h4 className="font-medium text-gray-900">Files to Review</h4>
          </div>
          <div className="space-y-2">
            {suspectRank.length > 0 ? (
              suspectRank.slice(0, 5).map((file, index) => (
                <div key={index} className="flex items-center p-2 bg-orange-50 rounded">
                  <Clock className="w-4 h-4 text-orange-600 mr-2" />
                  <div>
                    <p className="text-sm font-medium text-orange-900">{file}</p>
                    <p className="text-xs text-orange-700">Needs review</p>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-sm text-gray-500 italic">No files flagged for review</div>
            )}
          </div>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="mt-6 pt-6 border-t border-gray-200">
        <div className="grid grid-cols-3 gap-4 text-center">
          <div>
            <div className="text-2xl font-bold text-blue-600">{policies.length}</div>
            <div className="text-sm text-gray-600">Policies</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-green-600">{contracts.length}</div>
            <div className="text-sm text-gray-600">Contracts</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-orange-600">{suspectRank.length}</div>
            <div className="text-sm text-gray-600">Files to Review</div>
          </div>
        </div>
      </div>
    </div>
  );
}
