'use client';

import { useState } from 'react';
import { Upload, FileArchive, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { apiClient, IngestResponse, StatusPayload } from '@/lib/api';

interface RepositoryUploadProps {
  onUploadComplete?: (repoId: string) => void;
}

export default function RepositoryUpload({ onUploadComplete }: RepositoryUploadProps) {
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'processing' | 'complete' | 'error'>('idle');
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [repoId, setRepoId] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState('');

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (!file.name.endsWith('.zip')) {
      setUploadError('Please upload a ZIP file containing your repository');
      setUploadStatus('error');
      return;
    }

    setUploading(true);
    setUploadStatus('uploading');
    setUploadError(null);
    setProgress(0);
    setStatusMessage('Uploading repository...');

    try {
      // Upload the file
      const uploadResponse = await apiClient.ingestRepository(file);
      
      if (uploadResponse.error) {
        throw new Error(uploadResponse.error);
      }

      const { repoId: newRepoId, jobId } = uploadResponse.data as IngestResponse;
      setRepoId(newRepoId);
      setUploadStatus('processing');
      setStatusMessage('Processing repository...');

      // Poll for status updates
      await pollStatus(jobId);

    } catch (error) {
      console.error('Upload failed:', error);
      setUploadError(error instanceof Error ? error.message : 'Upload failed');
      setUploadStatus('error');
    } finally {
      setUploading(false);
    }
  };

  const pollStatus = async (jobId: string) => {
    const pollInterval = setInterval(async () => {
      try {
        const statusResponse = await apiClient.getStatus(jobId);
        
        if (statusResponse.error) {
          throw new Error(statusResponse.error);
        }

        const status = statusResponse.data as StatusPayload;
        setProgress(status.pct);
        
        const phaseMessages: Record<string, string> = {
          queued: 'Repository queued for processing...',
          acquiring: 'Acquiring repository data...',
          discovering: 'Discovering files and structure...',
          parsing: 'Parsing code files...',
          mapping: 'Mapping dependencies...',
          summarizing: 'Generating summaries...',
          done: 'Processing complete!',
          failed: 'Processing failed'
        };

        setStatusMessage(phaseMessages[status.phase] || `Processing... (${status.pct}%)`);

        if (status.phase === 'done') {
          clearInterval(pollInterval);
          setUploadStatus('complete');
          setProgress(100);
          onUploadComplete?.(status.repoId);
        } else if (status.phase === 'failed') {
          clearInterval(pollInterval);
          setUploadError(status.error || 'Processing failed');
          setUploadStatus('error');
        }
      } catch (error) {
        console.error('Status polling failed:', error);
        clearInterval(pollInterval);
        setUploadError('Failed to check processing status');
        setUploadStatus('error');
      }
    }, 2000); // Poll every 2 seconds
  };

  const getStatusIcon = () => {
    switch (uploadStatus) {
      case 'uploading':
      case 'processing':
        return <Loader2 className="w-6 h-6 animate-spin text-blue-500" />;
      case 'complete':
        return <CheckCircle className="w-6 h-6 text-green-500" />;
      case 'error':
        return <AlertCircle className="w-6 h-6 text-red-500" />;
      default:
        return <FileArchive className="w-6 h-6 text-gray-400" />;
    }
  };

  const getStatusColor = () => {
    switch (uploadStatus) {
      case 'uploading':
      case 'processing':
        return 'border-blue-200 bg-blue-50';
      case 'complete':
        return 'border-green-200 bg-green-50';
      case 'error':
        return 'border-red-200 bg-red-50';
      default:
        return 'border-gray-200 bg-gray-50';
    }
  };

  return (
    <div className="w-full max-w-3xl mx-auto">
      <div className={`border-2 border-dashed rounded-xl p-12 transition-colors ${getStatusColor()}`}>
        <div className="text-center">
          {getStatusIcon()}
          
          <h3 className="mt-6 text-2xl font-semibold text-gray-900">
            {uploadStatus === 'idle' && 'Ready to Analyze'}
            {uploadStatus === 'uploading' && 'Uploading Repository'}
            {uploadStatus === 'processing' && 'Analyzing Codebase'}
            {uploadStatus === 'complete' && 'Analysis Complete'}
            {uploadStatus === 'error' && 'Upload Failed'}
          </h3>
          
          <p className="mt-3 text-base text-gray-600 max-w-lg mx-auto">
            {uploadStatus === 'idle' && 'Drop your repository ZIP file here or click to browse. We\'ll analyze your codebase structure, dependencies, and data flow patterns.'}
            {uploadStatus === 'uploading' && 'Uploading your repository files...'}
            {uploadStatus === 'processing' && statusMessage}
            {uploadStatus === 'complete' && `Analysis complete! Repository ${repoId} is ready for exploration.`}
            {uploadStatus === 'error' && uploadError}
          </p>

          {uploadStatus === 'idle' && (
            <div className="mt-6">
              <label className="cursor-pointer">
                <input
                  type="file"
                  accept=".zip"
                  onChange={handleFileUpload}
                  className="hidden"
                  disabled={uploading}
                />
                <div className="inline-flex items-center px-6 py-3 border border-transparent text-base font-medium rounded-lg text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors shadow-sm">
                  <Upload className="w-5 h-5 mr-2" />
                  Choose Repository ZIP File
                </div>
              </label>
            </div>
          )}

          {uploadStatus === 'processing' && (
            <div className="mt-6">
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div 
                  className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p className="mt-2 text-sm text-gray-500">{progress}% complete</p>
            </div>
          )}

          {uploadStatus === 'complete' && (
            <div className="mt-6">
              <button
                onClick={() => {
                  setUploadStatus('idle');
                  setRepoId(null);
                  setProgress(0);
                  setStatusMessage('');
                }}
                className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
              >
                Upload Another Repository
              </button>
            </div>
          )}

          {uploadStatus === 'error' && (
            <div className="mt-6">
              <button
                onClick={() => {
                  setUploadStatus('idle');
                  setUploadError(null);
                  setProgress(0);
                  setStatusMessage('');
                }}
                className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
              >
                Try Again
              </button>
            </div>
          )}
        </div>
      </div>

      {repoId && uploadStatus === 'complete' && (
        <div className="mt-4 p-4 bg-green-50 border border-green-200 rounded-lg">
          <p className="text-sm text-green-800">
            <strong>Repository ID:</strong> {repoId}
          </p>
          <p className="text-xs text-green-600 mt-1">
            You can now explore the capabilities and structure of this repository.
          </p>
        </div>
      )}
    </div>
  );
}
