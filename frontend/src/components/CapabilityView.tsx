'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { ArrowLeft, RefreshCw, AlertCircle, CheckCircle } from 'lucide-react';
import { apiClient, CapabilityDetail, CapabilitySummary } from '@/lib/api';
import Legend from './capability/Legend';
import SectionTitle from './shared/SectionTitle';
import SwimlaneFlow from './capability/SwimlaneFlow';
import DataFlowBar from './capability/DataFlowBar';
import FlowGraph from './capability/FlowGraph';
import FileCard from './capability/FileCard';
import TestsPanel from './capability/TestsPanel';
import DataItemExplanation from './capability/DataItemExplanation';
import QAInterface from './QAInterface';

interface CapabilityViewProps {
  repoId: string;
  capabilities: CapabilitySummary[];
  onCapabilityChange?: (capability: CapabilitySummary) => void;
}

export default function CapabilityView({ 
  repoId, 
  capabilities, 
  onCapabilityChange 
}: CapabilityViewProps) {
  const [selectedCapability, setSelectedCapability] = useState<CapabilityDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // Load detailed capability data when component mounts or repoId changes
  useEffect(() => {
    if (capabilities.length > 0) {
      loadCapabilityDetails(capabilities[0].id);
    }
  }, [repoId, capabilities]);

  const loadCapabilityDetails = async (capId: string) => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await apiClient.getCapability(repoId, capId);
      
      if (response.error) {
        throw new Error(response.error);
      }
      
      setSelectedCapability(response.data as CapabilityDetail);
    } catch (err) {
      console.error('Failed to load capability details:', err);
      setError(err instanceof Error ? err.message : 'Failed to load capability details');
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    if (!selectedCapability) return;
    
    setRefreshing(true);
    try {
      // Trigger capability rebuild
      await apiClient.buildCapabilities(repoId);
      // Reload the capability details
      await loadCapabilityDetails(selectedCapability.id);
    } catch (err) {
      console.error('Failed to refresh capability:', err);
    } finally {
      setRefreshing(false);
    }
  };

  const handleCapabilitySelect = (capability: CapabilitySummary) => {
    loadCapabilityDetails(capability.id);
  };

  if (loading && !selectedCapability) {
    return (
      <div className="w-full max-w-7xl mx-auto">
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading capability details...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full max-w-7xl mx-auto">
        <div className="text-center py-12">
          <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">Failed to load capability</h3>
          <p className="text-gray-600 mb-4">{error}</p>
          <button
            onClick={() => selectedCapability && loadCapabilityDetails(selectedCapability.id)}
            className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  if (!selectedCapability) {
    return (
      <div className="w-full max-w-7xl mx-auto">
        <div className="text-center py-12">
          <p className="text-gray-600">No capability selected</p>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">{selectedCapability.name}</h1>
            <p className="mt-2 text-lg text-gray-600">{selectedCapability.purpose}</p>
            <p className="mt-1 text-sm text-gray-500">Repository: {repoId}</p>
          </div>
          
          <div className="flex items-center space-x-3">
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        </div>

        {/* Capability selector */}
        {capabilities.length > 1 && (
          <div className="mt-6">
            <h3 className="text-sm font-medium text-gray-900 mb-3">Available Capabilities:</h3>
            <div className="flex flex-wrap gap-2">
              {capabilities.map((cap) => (
                <button
                  key={cap.id}
                  onClick={() => handleCapabilitySelect(cap)}
                  className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    selectedCapability.id === cap.id
                      ? 'bg-blue-100 text-blue-700 border border-blue-300'
                      : 'bg-gray-100 text-gray-700 border border-gray-300 hover:bg-gray-200'
                  }`}
                >
                  {cap.name}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="mb-8">
        <Legend />
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column - Flow and Steps */}
        <div className="lg:col-span-2 space-y-8">
          {/* Swimlane Flow */}
          <section>
            <SectionTitle title="Application Flow" />
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <SwimlaneFlow 
                swimlanes={selectedCapability.swimlanes}
                nodeIndex={selectedCapability.nodeIndex}
                controlFlow={selectedCapability.controlFlow}
                steps={selectedCapability.steps}
              />
            </div>
          </section>

          {/* Data Flow */}
          <section>
            <SectionTitle title="Data Flow" />
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <DataFlowBar 
                dataFlow={selectedCapability.dataFlow}
                sources={selectedCapability.sources}
                sinks={selectedCapability.sinks}
              />
            </div>
          </section>

          {/* Flow Graph */}
          <section>
            <SectionTitle title="Flow Graph" />
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <FlowGraph 
                dataFlow={selectedCapability.dataFlow}
                controlFlow={selectedCapability.controlFlow}
                nodeIndex={selectedCapability.nodeIndex}
              />
            </div>
          </section>
        </div>

        {/* Right Column - Details and Files */}
        <div className="space-y-8">
          {/* Entry Points */}
          <section>
            <SectionTitle title="Entry Points" />
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <div className="space-y-3">
                {selectedCapability.entryPoints.map((entryPoint, index) => (
                  <div key={index} className="flex items-center p-3 bg-gray-50 rounded-lg">
                    <div className="flex-1">
                      <p className="text-sm font-medium text-gray-900">{entryPoint}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* Key Files */}
          <section>
            <SectionTitle title="Key Files" />
            <div className="space-y-3">
              {selectedCapability.keyFiles.map((file, index) => (
                <FileCard key={index} file={file} />
              ))}
            </div>
          </section>

          {/* Orchestrators */}
          <section>
            <SectionTitle title="Orchestrators" />
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <div className="space-y-3">
                {selectedCapability.orchestrators.map((orchestrator, index) => (
                  <div key={index} className="flex items-center p-3 bg-blue-50 rounded-lg">
                    <div className="flex-1">
                      <p className="text-sm font-medium text-blue-900">{orchestrator}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* Data In/Out */}
          <section>
            <SectionTitle title="Data Flow" />
            <div className="space-y-4">
              <DataItemExplanation 
                title="Data In"
                items={selectedCapability.dataIn}
                color="green"
              />
              <DataItemExplanation 
                title="Data Out"
                items={selectedCapability.dataOut}
                color="blue"
              />
            </div>
          </section>

          {/* Tests */}
          <section>
            <SectionTitle title="Tests & Validation" />
            <div className="bg-white rounded-lg border border-gray-200">
              <TestsPanel 
                policies={selectedCapability.policies}
                contracts={selectedCapability.contracts}
                suspectRank={selectedCapability.suspectRank}
              />
            </div>
          </section>

          {/* QA Interface */}
          <section>
            <SectionTitle title="Ask Questions" />
            <QAInterface repoId={repoId} />
          </section>
        </div>
      </div>
    </div>
  );
}
