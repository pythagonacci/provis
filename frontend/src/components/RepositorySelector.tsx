'use client';

import { useState, useEffect } from 'react';
import { Database, FolderOpen, Clock, CheckCircle, AlertCircle } from 'lucide-react';
import { apiClient, CapabilitySummary } from '@/lib/api';

interface RepositorySelectorProps {
  onRepositorySelect: (repoId: string, capabilities: CapabilitySummary[]) => void;
}

interface Repository {
  id: string;
  name: string;
  lastAnalyzed?: string;
  capabilities: CapabilitySummary[];
  status: 'ready' | 'processing' | 'error';
}

export default function RepositorySelector({ onRepositorySelect }: RepositorySelectorProps) {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // For demo purposes, we'll create some mock repositories
  // In a real app, you'd fetch these from the API
  useEffect(() => {
    const loadRepositories = async () => {
      setLoading(true);
      try {
        // Mock repositories for demo
        const mockRepos: Repository[] = [
          {
            id: 'demo-repo-1',
            name: 'E-commerce Platform',
            lastAnalyzed: '2024-01-15T10:30:00Z',
            capabilities: [
              {
                id: 'cap_main_workflow',
                name: 'Main Application Workflow',
                purpose: 'Primary e-commerce functionality including product catalog, cart, and checkout',
                entryPoints: ['/api/products', '/api/cart', '/api/checkout'],
                keyFiles: ['app/products/page.tsx', 'app/cart/page.tsx', 'app/checkout/page.tsx'],
                dataIn: ['ProductCatalog', 'UserSession', 'PaymentInfo'],
                dataOut: ['OrderConfirmation', 'Receipt', 'InventoryUpdate'],
                sources: ['Database', 'PaymentGateway', 'InventoryService'],
                sinks: ['EmailService', 'Analytics', 'Logging']
              }
            ],
            status: 'ready'
          },
          {
            id: 'demo-repo-2',
            name: 'Content Management System',
            lastAnalyzed: '2024-01-14T15:45:00Z',
            capabilities: [
              {
                id: 'cap_main_workflow',
                name: 'CMS Workflow',
                purpose: 'Content creation, editing, and publishing workflow',
                entryPoints: ['/api/content', '/api/media', '/api/publish'],
                keyFiles: ['app/content/page.tsx', 'app/media/page.tsx', 'components/Editor.tsx'],
                dataIn: ['ContentData', 'MediaFiles', 'UserPermissions'],
                dataOut: ['PublishedContent', 'MediaURLs', 'AuditLog'],
                sources: ['Database', 'FileStorage', 'AuthService'],
                sinks: ['CDN', 'SearchIndex', 'NotificationService']
              }
            ],
            status: 'ready'
          },
          {
            id: 'demo-repo-3',
            name: 'Analytics Dashboard',
            lastAnalyzed: '2024-01-13T09:15:00Z',
            capabilities: [
              {
                id: 'cap_main_workflow',
                name: 'Analytics Pipeline',
                purpose: 'Data collection, processing, and visualization workflow',
                entryPoints: ['/api/events', '/api/metrics', '/api/reports'],
                keyFiles: ['app/dashboard/page.tsx', 'components/Charts.tsx', 'lib/analytics.ts'],
                dataIn: ['EventData', 'Metrics', 'UserBehavior'],
                dataOut: ['Reports', 'Insights', 'Alerts'],
                sources: ['EventStream', 'Database', 'ExternalAPIs'],
                sinks: ['Dashboard', 'EmailAlerts', 'DataWarehouse']
              }
            ],
            status: 'ready'
          }
        ];

        setRepositories(mockRepos);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load repositories');
      } finally {
        setLoading(false);
      }
    };

    loadRepositories();
  }, []);

  const getStatusIcon = (status: Repository['status']) => {
    switch (status) {
      case 'ready':
        return <CheckCircle className="w-4 h-4 text-green-500" />;
      case 'processing':
        return <Clock className="w-4 h-4 text-blue-500" />;
      case 'error':
        return <AlertCircle className="w-4 h-4 text-red-500" />;
    }
  };

  const getStatusColor = (status: Repository['status']) => {
    switch (status) {
      case 'ready':
        return 'border-green-200 bg-green-50 hover:bg-green-100';
      case 'processing':
        return 'border-blue-200 bg-blue-50 hover:bg-blue-100';
      case 'error':
        return 'border-red-200 bg-red-50 hover:bg-red-100';
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  if (loading) {
    return (
      <div className="w-full max-w-4xl mx-auto">
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading repositories...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full max-w-4xl mx-auto">
        <div className="text-center py-12">
          <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">Failed to load repositories</h3>
          <p className="text-gray-600">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-4xl mx-auto">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-900 mb-2">Select Repository</h2>
        <p className="text-gray-600">Choose a repository to explore its capabilities and data flow</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {repositories.map((repo) => (
          <div
            key={repo.id}
            className={`border rounded-lg p-6 cursor-pointer transition-all duration-200 ${getStatusColor(repo.status)}`}
            onClick={() => onRepositorySelect(repo.id, repo.capabilities)}
          >
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center">
                <Database className="w-6 h-6 text-gray-600 mr-3" />
                <div>
                  <h3 className="font-semibold text-gray-900">{repo.name}</h3>
                  <p className="text-sm text-gray-500">ID: {repo.id}</p>
                </div>
              </div>
              {getStatusIcon(repo.status)}
            </div>

            <div className="space-y-2">
              <div className="flex items-center text-sm text-gray-600">
                <FolderOpen className="w-4 h-4 mr-2" />
                {repo.capabilities.length} capability{repo.capabilities.length !== 1 ? 'ies' : ''}
              </div>
              
              {repo.lastAnalyzed && (
                <div className="flex items-center text-sm text-gray-600">
                  <Clock className="w-4 h-4 mr-2" />
                  {formatDate(repo.lastAnalyzed)}
                </div>
              )}
            </div>

            <div className="mt-4 pt-4 border-t border-gray-200">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-900">Status</span>
                <span className={`text-sm font-medium ${
                  repo.status === 'ready' ? 'text-green-600' :
                  repo.status === 'processing' ? 'text-blue-600' :
                  'text-red-600'
                }`}>
                  {repo.status}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {repositories.length === 0 && (
        <div className="text-center py-12">
          <Database className="w-12 h-12 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">No repositories found</h3>
          <p className="text-gray-600">Upload a repository to get started with capability analysis.</p>
        </div>
      )}
    </div>
  );
}
