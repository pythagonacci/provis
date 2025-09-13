'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import RepositoryUpload from '@/components/RepositoryUpload';
import CapabilityView from '@/components/CapabilityView';
import { CapabilitySummary, apiClient } from '@/lib/api';

export default function Dashboard() {
  const [currentView, setCurrentView] = useState<'upload' | 'capability'>('upload');
  const [selectedRepoId, setSelectedRepoId] = useState<string | null>(null);
  const [selectedCapabilities, setSelectedCapabilities] = useState<CapabilitySummary[]>([]);

  const handleUploadComplete = (repoId: string) => {
    setSelectedRepoId(repoId);
    // Load capabilities for the uploaded repository
    loadCapabilities(repoId);
  };

  const loadCapabilities = async (repoId: string) => {
    try {
      const response = await apiClient.getCapabilities(repoId);
      if (response.data) {
        setSelectedCapabilities(response.data);
        setCurrentView('capability');
      }
    } catch (error) {
      console.error('Failed to load capabilities:', error);
      // Still show capability view even if loading fails
      setCurrentView('capability');
    }
  };

  const handleBackToUpload = () => {
    setCurrentView('upload');
    setSelectedRepoId(null);
    setSelectedCapabilities([]);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <h1 className="text-xl font-bold text-gray-900">Provis Dashboard</h1>
            </div>
            
            <nav className="flex space-x-4">
              <button
                onClick={() => setCurrentView('upload')}
                className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  currentView === 'upload'
                    ? 'bg-blue-100 text-blue-700'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                Upload Repository
              </button>
              {selectedRepoId && (
                <button
                  onClick={() => setCurrentView('capability')}
                  className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    currentView === 'capability'
                      ? 'bg-blue-100 text-blue-700'
                      : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  View Analysis
                </button>
              )}
            </nav>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <motion.div
          key={currentView}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          transition={{ duration: 0.3 }}
        >
          {currentView === 'upload' && (
            <div className="text-center">
              <div className="mb-8">
                <h2 className="text-3xl font-bold text-gray-900 mb-4">Analyze Your Repository</h2>
                <p className="text-lg text-gray-600 max-w-2xl mx-auto">
                  Upload a ZIP file of your repository to discover its capabilities, data flow, and architecture patterns.
                </p>
              </div>
              <RepositoryUpload onUploadComplete={handleUploadComplete} />
            </div>
          )}

          {currentView === 'capability' && selectedRepoId && (
            <div>
              <div className="mb-8">
                <button
                  onClick={handleBackToUpload}
                  className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                >
                  ← Upload Another Repository
                </button>
              </div>
              <CapabilityView
                repoId={selectedRepoId}
                capabilities={selectedCapabilities}
                onCapabilityChange={() => {
                  // Handle capability updates if needed
                }}
              />
            </div>
          )}
        </motion.div>
      </main>
    </div>
  );
}