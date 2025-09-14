"use client";

import React, { useState, useEffect, useMemo } from "react";
import { Folder, File, GitBranch, Globe, Package, ListTree, ChevronRight, Upload, RefreshCw, AlertCircle, CheckCircle, Search, PanelsTopLeft, ExternalLink } from "lucide-react";
import { apiClient, CapabilitySummary, CapabilityDetail } from "@/lib/api";
import { useRouter } from "next/navigation";

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full border border-white/15 bg-white/5 px-2 py-0.5 text-[10px] text-white/80">
      {children}
    </span>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-md bg-white/10 px-2 py-0.5 text-xs text-white/80">
      {children}
    </span>
  );
}

function SectionTitle({ icon: Icon, title }: { icon: any; title: string }) {
  return (
    <div className="flex items-center gap-2 text-white/90">
      <Icon size={16} className="opacity-80" />
      <h3 className="text-sm font-medium tracking-wide">{title}</h3>
    </div>
  );
}

// Legend component
function Legend() {
  return (
    <div className="mb-6 rounded-2xl border border-white/10 bg-white/5 p-4 text-white/90">
      <SectionTitle icon={PanelsTopLeft} title="Legend" />
      <div className="mt-3 grid grid-cols-1 gap-4 text-xs md:grid-cols-2">
        <div>
          <div className="mb-2 font-medium text-white/80">Side-effects badges</div>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Badge>io</Badge>
              <span className="text-white/60">filesystem / streams</span>
            </div>
            <div className="flex items-center gap-2">
              <Badge>net</Badge>
              <span className="text-white/60">HTTP / fetch / sockets</span>
            </div>
            <div className="flex items-center gap-2">
              <Badge>db</Badge>
              <span className="text-white/60">database queries</span>
            </div>
            <div className="flex items-center gap-2">
              <Badge>dom</Badge>
              <span className="text-white/60">DOM mutations</span>
            </div>
            <div className="flex items-center gap-2">
              <Badge>render</Badge>
              <span className="text-white/60">HTML/JSX/SSR output</span>
            </div>
          </div>
        </div>
        <div>
          <div className="mb-2 font-medium text-white/80">Role badges</div>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Badge>Entry point</Badge>
              <span className="text-white/60">receives request / starts flow</span>
            </div>
            <div className="flex items-center gap-2">
              <Badge>Orchestrator</Badge>
              <span className="text-white/60">coordinates other modules</span>
            </div>
            <div className="flex items-center gap-2">
              <Badge>Source</Badge>
              <span className="text-white/60">reads data / config</span>
            </div>
            <div className="flex items-center gap-2">
              <Badge>Sink</Badge>
              <span className="text-white/60">writes output / responds</span>
            </div>
            <div className="flex items-center gap-2">
              <Badge>Key file</Badge>
              <span className="text-white/60">high-impact edit target</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------- Type definitions ----------
export type FileNode = { 
  id: string; 
  label: string; 
  purpose: string; 
  lines: number;
  role?: string;
  lane?: string;
};

export type FolderNode = { 
  id: string; 
  label: string; 
  purpose: string; 
  children?: (FolderNode | FileNode)[] 
};

type CapabilityStep = {
  title: string;
  description: string;
  fileId?: string;
};

type Capability = {
  id: string;
  name: string;
  desc: string;
  steps: CapabilityStep[];
  entryPoints: string[];
  keyFiles: string[];
  dataIn: string[];
  dataOut: string[];
  sources: string[];
  sinks: string[];
};

// ---------- Upload Interface ----------
function UploadInterface({ onComplete }: { onComplete: (repoId: string) => void }) {
  const [status, setStatus] = useState<'idle' | 'uploading' | 'processing' | 'complete' | 'error'>('idle');
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (!file.name.endsWith('.zip')) {
      setError('Please upload a ZIP file containing your repository');
      setStatus('error');
      return;
    }

    setStatus('uploading');
    setProgress(0);
    setError('');
    setMessage('Uploading repository...');

    try {
      const uploadResponse = await apiClient.ingestRepository(file);
      
      if (uploadResponse.error) {
        throw new Error(uploadResponse.error);
      }

      const { repoId, jobId } = uploadResponse.data!;
      setStatus('processing');
      setMessage('Processing repository...');

      // Poll for status updates
      const pollInterval = setInterval(async () => {
        try {
          const statusResponse = await apiClient.getStatus(jobId);
          
          if (statusResponse.error) {
            throw new Error(statusResponse.error);
          }

          const statusData = statusResponse.data!;
          setProgress(statusData.pct);
          
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

          setMessage(phaseMessages[statusData.phase] || `Processing... (${statusData.pct}%)`);

          if (statusData.phase === 'done') {
            clearInterval(pollInterval);
            setStatus('complete');
            setProgress(100);
            onComplete(repoId);
          } else if (statusData.phase === 'failed') {
            clearInterval(pollInterval);
            setError(statusData.error || 'Processing failed');
            setStatus('error');
          }
        } catch (error) {
          console.error('Status polling failed:', error);
          clearInterval(pollInterval);
          setError('Failed to check processing status');
          setStatus('error');
        }
      }, 2000);

    } catch (error) {
      console.error('Upload failed:', error);
      setError(error instanceof Error ? error.message : 'Upload failed');
      setStatus('error');
    }
  };

  const getStatusIcon = () => {
    switch (status) {
      case 'uploading':
      case 'processing':
        return <RefreshCw className="w-6 h-6 animate-spin text-emerald-400" />;
      case 'complete':
        return <CheckCircle className="w-6 h-6 text-emerald-400" />;
      case 'error':
        return <AlertCircle className="w-6 h-6 text-red-400" />;
      default:
        return <Upload className="w-6 h-6 text-white/60" />;
    }
  };

  if (status === 'complete') {
    return (
      <div className="text-center py-12">
        <div className="w-16 h-16 bg-emerald-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
          <CheckCircle className="w-8 h-8 text-emerald-400" />
        </div>
        <h2 className="text-2xl font-bold text-white mb-2">Repository Ready!</h2>
        <p className="text-white/70 mb-6">Your repository has been analyzed and is ready for exploration.</p>
        <button
          onClick={() => {
            setStatus('idle');
            setProgress(0);
            setMessage('');
            setError('');
          }}
          className="inline-flex items-center px-4 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors"
        >
          Upload Another Repository
        </button>
      </div>
    );
  }

  return (
    <div className="text-center py-12">
      <div className="w-16 h-16 bg-white/10 rounded-full flex items-center justify-center mx-auto mb-6">
        {getStatusIcon()}
      </div>
      
      <h2 className="text-2xl font-bold text-white mb-2">
        {status === 'idle' && 'Drop a Repository'}
        {status === 'uploading' && 'Uploading Repository'}
        {status === 'processing' && 'Analyzing Codebase'}
        {status === 'error' && 'Upload Failed'}
      </h2>
      
      <p className="text-white/70 mb-8 max-w-md mx-auto">
        {status === 'idle' && 'Upload a ZIP file to analyze your repository\'s architecture, API endpoints, data models, and capabilities.'}
        {status === 'uploading' && 'Uploading your repository files...'}
        {status === 'processing' && message}
        {status === 'error' && error}
      </p>

      {status === 'idle' && (
        <label className="cursor-pointer">
          <input
            type="file"
            accept=".zip"
            onChange={handleFileUpload}
            className="hidden"
          />
          <div className="inline-flex items-center px-6 py-3 bg-emerald-500/20 text-emerald-200 rounded-xl hover:bg-emerald-500/30 transition-colors border border-emerald-500/30">
            <Upload className="w-5 h-5 mr-2" />
            Choose Repository ZIP File
          </div>
        </label>
      )}

      {status === 'processing' && (
        <div className="max-w-md mx-auto">
          <div className="w-full bg-white/10 rounded-full h-2 mb-4">
            <div 
              className="bg-emerald-400 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-sm text-white/60">{progress}% complete</p>
        </div>
      )}

      {status === 'error' && (
        <button
          onClick={() => {
            setStatus('idle');
            setError('');
            setMessage('');
            setProgress(0);
          }}
          className="inline-flex items-center px-4 py-2 bg-red-500/20 text-red-200 rounded-lg hover:bg-red-500/30 transition-colors border border-red-500/30"
        >
          Try Again
        </button>
      )}
    </div>
  );
}

// ---------- Recursive folder/file viewer ----------
function FolderTree({ node, onSelect }: { node: FolderNode | FileNode; onSelect: (n: FolderNode | FileNode) => void | Promise<void> }) {
  const isFolder = (n: any): n is FolderNode => (n as FolderNode).children !== undefined;
  
  if (isFolder(node)) {
    return (
      <div className="ml-2 mt-1">
        <button onClick={() => onSelect(node)} className="flex items-center gap-2 text-sm text-white/90 hover:underline">
          <Folder size={14} /> {node.label}
        </button>
        <div className="ml-4 border-l border-white/10 pl-2">
          {node.children?.map((c) => (
            <FolderTree key={c.id} node={c} onSelect={onSelect} />
          ))}
        </div>
      </div>
    );
  }
  
  return (
    <div className="ml-6 mt-1 flex items-center gap-2 text-xs text-white/70">
      <File size={12} className="opacity-70" />
      <button onClick={() => onSelect(node)} className="hover:underline">{node.label}</button>
    </div>
  );
}

// ---------- File block display ----------
function FileBlock({ file }: { file: FileNode }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/5 p-2">
      <div className="text-xs font-medium text-white/90 flex items-center gap-2">
        <File size={12} /> {file.label}
      </div>
      <div className="mt-1 text-[11px] text-white/60">{file.purpose}</div>
      <div className="mt-1 text-[10px] text-white/50">
        {file.role && file.lane && `${file.role} • ${file.lane}`}
        {file.lines && ` • ~${file.lines} LOC`}
      </div>
    </div>
  );
}

// ---------- Enhanced File Details with LLM Summary ----------
function FileDetails({ 
  file, 
  fileContent, 
  loadingFile 
}: { 
  file: FileNode; 
  fileContent: any; 
  loadingFile: boolean; 
}) {
  return (
    <div className="space-y-4">
      <FileBlock file={file} />
      
      {/* LLM Summary Section */}
      <div className="rounded-lg border border-white/10 bg-white/5 p-3">
        <div className="flex items-center gap-2 mb-3">
          <File size={14} className="text-emerald-400" />
          <h4 className="text-sm font-medium text-white/90">AI Summary</h4>
        </div>
        
        {loadingFile ? (
          <div className="flex items-center gap-2 text-white/60">
            <RefreshCw className="w-4 h-4 animate-spin" />
            <span className="text-xs">Loading file analysis...</span>
          </div>
        ) : fileContent ? (
          <div className="space-y-3">
            {(fileContent.dev_summary || fileContent.blurb || fileContent.summary) && (
              <div>
                <div className="text-xs font-medium text-white/80 mb-1">Purpose</div>
                <div className="text-xs text-white/70 bg-black/20 p-2 rounded">
                  {fileContent.dev_summary || fileContent.blurb || fileContent.summary}
                </div>
              </div>
            )}
            
            {fileContent.vibecoder_summary && fileContent.vibecoder_summary !== "This file is part of the application." && (
              <div>
                <div className="text-xs font-medium text-white/80 mb-1">In Plain English</div>
                <div className="text-xs text-white/70 bg-emerald-500/10 border border-emerald-500/20 p-2 rounded">
                  {fileContent.vibecoder_summary}
                </div>
              </div>
            )}
            
            {fileContent.how_to_modify && fileContent.how_to_modify !== "Edit this file to modify its functionality." && (
              <div>
                <div className="text-xs font-medium text-white/80 mb-1">How to Modify</div>
                <div className="text-xs text-white/70 bg-blue-500/10 border border-blue-500/20 p-2 rounded">
                  {fileContent.how_to_modify}
                </div>
              </div>
            )}
            
            {fileContent.risks && fileContent.risks !== "Be careful when modifying this file." && (
              <div>
                <div className="text-xs font-medium text-white/80 mb-1">Risks & Warnings</div>
                <div className="text-xs text-white/70 bg-red-500/10 border border-red-500/20 p-2 rounded">
                  {fileContent.risks}
                </div>
              </div>
            )}
            
            {fileContent.exports && fileContent.exports.length > 0 && (
              <div>
                <div className="text-xs font-medium text-white/80 mb-1">Exports</div>
                <div className="flex flex-wrap gap-1">
                  {fileContent.exports.map((exp: string, idx: number) => (
                    <Badge key={idx}>{exp}</Badge>
                  ))}
                </div>
              </div>
            )}
            
            {fileContent.imports && fileContent.imports.length > 0 && (
              <div>
                <div className="text-xs font-medium text-white/80 mb-1">Key Imports</div>
                <div className="flex flex-wrap gap-1">
                  {fileContent.imports.slice(0, 5).map((imp: string, idx: number) => (
                    <Badge key={idx}>{imp.split('/').pop() || imp}</Badge>
                  ))}
                  {fileContent.imports.length > 5 && (
                    <Badge>+{fileContent.imports.length - 5} more</Badge>
                  )}
                </div>
              </div>
            )}
            
            {fileContent.functions && fileContent.functions.length > 0 && (
              <div>
                <div className="text-xs font-medium text-white/80 mb-1">Functions ({fileContent.functions.length})</div>
                <div className="space-y-1 max-h-32 overflow-y-auto">
                  {fileContent.functions.slice(0, 3).map((func: any, idx: number) => (
                    <div key={idx} className="text-xs bg-black/20 p-2 rounded">
                      <div className="font-medium text-white/90">{func.name}</div>
                      <div className="text-white/60">{func.summary}</div>
                    </div>
                  ))}
                  {fileContent.functions.length > 3 && (
                    <div className="text-xs text-white/50 text-center py-1">
                      ... and {fileContent.functions.length - 3} more functions
                    </div>
                  )}
                </div>
              </div>
            )}
            
            {fileContent.loc && (
              <div className="flex justify-between text-xs text-white/50">
                <span>Lines of code: {fileContent.loc}</span>
                <span>Type: {fileContent.lang || 'Unknown'}</span>
              </div>
            )}
          </div>
        ) : (
          <div className="text-xs text-white/50 text-center py-4">
            Click on a file to see its AI-generated summary and analysis
          </div>
        )}
      </div>
    </div>
  );
}

// ---------- Capability Steps Panel ----------
function CapabilitySteps({ 
  capability, 
  onFileSelect, 
  qaResponse, 
  onRunQuery, 
  loading 
}: { 
  capability: Capability | null; 
  onFileSelect: (fileId: string) => Promise<void>;
  qaResponse: string | null;
  onRunQuery: (query: string) => Promise<void>;
  loading: boolean;
}) {
  const [query, setQuery] = useState('');

  const handleAsk = async () => {
    if (!query.trim() || loading) return;
    await onRunQuery(query);
    setQuery('');
  };

  if (!capability) {
    return (
      <div className="space-y-4">
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-center text-white/60">
          <ListTree size={24} className="mx-auto mb-2 opacity-50" />
          <p className="text-sm">Select a capability to see its step-by-step process</p>
        </div>
        
        {/* Ask section */}
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <h3 className="text-sm font-semibold text-white/90 mb-3">Ask about this repository</h3>
          <div className="flex gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAsk()}
              placeholder="What does this repository do?"
              className="flex-1 bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-sm text-white placeholder:text-white/50 focus:outline-none focus:border-emerald-500/50"
            />
            <button
              onClick={handleAsk}
              disabled={loading || !query.trim()}
              className="px-4 py-2 bg-emerald-500/20 text-emerald-200 rounded-lg hover:bg-emerald-500/30 transition-colors border border-emerald-500/30 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {loading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Asking...
                </>
              ) : (
                'Ask'
              )}
            </button>
          </div>
          {qaResponse && (
            <div className="mt-3 p-3 bg-black/20 border border-white/10 rounded-lg">
              <div className="text-xs text-white/80 whitespace-pre-wrap max-h-40 overflow-auto">
                {qaResponse}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
        <div className="mb-3 flex items-center gap-2">
          <ListTree size={16} className="text-emerald-400" />
          <h3 className="text-sm font-semibold text-white/90">Narrated Steps</h3>
        </div>
        
        {/* Capability header */}
        <div className="mb-4 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
          <div className="text-sm font-medium text-emerald-200">{capability.name}</div>
          <div className="text-xs text-emerald-200/70">{capability.desc}</div>
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            <Badge>Entry: {capability.entryPoints.join(", ")}</Badge>
            <Badge>Data in: {capability.dataIn.join(", ")}</Badge>
            <Badge>Data out: {capability.dataOut.join(", ")}</Badge>
          </div>
        </div>

        {/* Steps */}
        <div className="space-y-3">
          {capability.steps.map((step, index) => (
            <div
              key={index}
              className={`flex items-start gap-3 rounded-lg p-3 transition-colors ${
                step.fileId ? 'cursor-pointer hover:bg-white/5' : ''
              }`}
              onClick={() => step.fileId && onFileSelect(step.fileId)}
            >
              <div className="mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-emerald-500/20 text-xs font-medium text-emerald-200">
                {index + 1}
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-white/90">{step.title}</span>
                  {step.fileId && <ChevronRight size={12} className="text-white/40" />}
                </div>
                <div className="mt-1 text-xs text-white/70">{step.description}</div>
                {step.fileId && (
                  <div className="mt-1 flex items-center gap-1 text-xs text-emerald-300/60">
                    <File size={10} />
                    {step.fileId}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Ask section */}
      <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
        <h3 className="text-sm font-semibold text-white/90 mb-3">Ask about "{capability.name}"</h3>
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAsk()}
            placeholder={`How does ${capability.name} work?`}
            className="flex-1 bg-white/10 border border-white/20 rounded-lg px-3 py-2 text-sm text-white placeholder:text-white/50 focus:outline-none focus:border-emerald-500/50"
          />
          <button
            onClick={handleAsk}
            disabled={loading || !query.trim()}
            className="px-4 py-2 bg-emerald-500/20 text-emerald-200 rounded-lg hover:bg-emerald-500/30 transition-colors border border-emerald-500/30 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {loading ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Asking...
              </>
            ) : (
              'Ask'
            )}
          </button>
        </div>
        {qaResponse && (
          <div className="mt-3 p-3 bg-black/20 border border-white/10 rounded-lg">
            <div className="text-xs text-white/80 whitespace-pre-wrap max-h-40 overflow-auto">
              {qaResponse}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------- Main Overview ----------
export default function RepoOverviewMockup() {
  const router = useRouter();
  
  // Real data states
  const [repoId, setRepoId] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<CapabilitySummary[]>([]);
  const [currentCapability, setCurrentCapability] = useState<CapabilityDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [qaResponse, setQaResponse] = useState<string | null>(null);

  // UI states
  const [focus, setFocus] = useState<FolderNode | FileNode | null>(null);
  const [selectedCapability, setSelectedCapability] = useState<Capability | null>(null);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"understand" | "fix" | "add" | "remove">("understand");
  const [novice, setNovice] = useState<boolean>(true);
  const [fileContent, setFileContent] = useState<any>(null);
  const [loadingFile, setLoadingFile] = useState(false);

  // Build repository tree from nodeIndex
  const repoTree = useMemo((): FolderNode => {
    if (!currentCapability?.nodeIndex) {
      return {
        id: "root",
        label: "/",
        purpose: "Repository root",
        children: []
      };
    }

    const files = Object.entries(currentCapability.nodeIndex).map(([path, node]) => ({
      id: path,
      label: path.split('/').pop() || path,
      purpose: `${node.role} component in ${node.lane} layer`,
      lines: 0, // We don't have line count from the backend
      role: node.role,
      lane: node.lane
    }));

    // Group files by directory structure
    const dirMap: { [key: string]: FileNode[] } = {};
    files.forEach(file => {
      const dir = file.id.includes('/') ? file.id.split('/').slice(0, -1).join('/') : 'root';
      if (!dirMap[dir]) dirMap[dir] = [];
      dirMap[dir].push(file);
    });

    // Create folder structure
    const children: (FolderNode | FileNode)[] = [];
    
    // Add files in root
    if (dirMap['root']) {
      children.push(...dirMap['root']);
    }

    // Add directories
    Object.entries(dirMap).forEach(([dir, dirFiles]) => {
      if (dir !== 'root') {
        children.push({
          id: dir,
          label: dir.split('/').pop() || dir,
          purpose: `Directory containing ${dirFiles.length} files`,
          children: dirFiles
        });
      }
    });

    return {
      id: "root",
      label: "/",
      purpose: "Repository root",
      children
    };
  }, [currentCapability]);

  // Convert capabilities to UI format
  const uiCapabilities = useMemo((): Capability[] => {
    return capabilities.map(cap => ({
      id: cap.id,
      name: cap.name,
      desc: cap.purpose,
      steps: [],
      entryPoints: cap.entryPoints,
      keyFiles: cap.keyFiles,
      dataIn: cap.dataIn,
      dataOut: cap.dataOut,
      sources: cap.sources,
      sinks: cap.sinks
    }));
  }, [capabilities]);

  // Extract integrations and dependencies from data
  const integrations = useMemo(() => {
    if (!currentCapability) return [];
    return currentCapability.dataFlow?.externals?.map(ext => ext.name) || [];
  }, [currentCapability]);

  const dependencies = useMemo(() => {
    if (!currentCapability?.nodeIndex) return [];
    // Extract package names from imports that look like dependencies
    const deps = new Set<string>();
    Object.values(currentCapability.nodeIndex).forEach(node => {
      node.incoming.forEach(inc => {
        if (inc.includes('node_modules') || inc.startsWith('@') || !inc.includes('/')) {
          deps.add(inc.split('/')[0]);
        }
      });
    });
    return Array.from(deps).slice(0, 8); // Limit to first 8
  }, [currentCapability]);

  // Load repository data
  const loadRepositoryData = async (newRepoId: string) => {
    setLoading(true);
    try {
      // Load capabilities
      const capabilitiesResponse = await apiClient.getCapabilities(newRepoId);
      if (capabilitiesResponse.data) {
        setCapabilities(capabilitiesResponse.data);
        
        // Load first capability detail if available
        if (capabilitiesResponse.data.length > 0) {
          const firstCap = capabilitiesResponse.data[0];
          const detailResponse = await apiClient.getCapability(newRepoId, firstCap.id);
          if (detailResponse.data) {
            setCurrentCapability(detailResponse.data);
          }
        }
      }
    } catch (error) {
      console.error('Failed to load repository data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleUploadComplete = async (newRepoId: string) => {
    setRepoId(newRepoId);
    await loadRepositoryData(newRepoId);
  };

  // Mode detection from query
  const detectMode = (q: string) => {
    const lower = q.toLowerCase();
    if (/(fix|bug|issue|error)/.test(lower)) return "fix" as const;
    if (/add|implement/.test(lower)) return "add" as const;
    if (/remove|delete|deprecate/.test(lower)) return "remove" as const;
    return "understand" as const;
  };

  const runQuery = async () => {
    if (!query.trim() || !repoId) return;
    
    setMode(detectMode(query));
    await handleRunQuery(query);
  };

  const handleCapabilitySelect = async (capability: Capability) => {
    if (!repoId) return;
    
    setLoading(true);
    try {
      const detailResponse = await apiClient.getCapability(repoId, capability.id);
      if (detailResponse.data) {
        const convertedCap: Capability = {
          id: detailResponse.data.id,
          name: detailResponse.data.name,
          desc: detailResponse.data.purpose,
          entryPoints: detailResponse.data.entryPoints,
          keyFiles: detailResponse.data.keyFiles,
          dataIn: detailResponse.data.dataIn,
          dataOut: detailResponse.data.dataOut,
          sources: detailResponse.data.sources,
          sinks: detailResponse.data.sinks,
          steps: detailResponse.data.steps || []
        };
        setSelectedCapability(convertedCap);
      }
    } catch (error) {
      console.error('Failed to load capability details:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCapabilityDashboard = (capabilityId: string) => {
    router.push(`/capability/${capabilityId}`);
  };

  const loadFileContent = async (filePath: string) => {
    if (!repoId) return null;
    
    setLoadingFile(true);
    try {
      const response = await apiClient.getFile(repoId, filePath);
      if (response.data) {
        setFileContent(response.data);
        return response.data;
      }
    } catch (error) {
      console.error('Failed to load file content:', error);
    } finally {
      setLoadingFile(false);
    }
    return null;
  };

  const handleFileSelect = async (fileId: string) => {
    if (!currentCapability?.nodeIndex[fileId]) return;
    
    const node = currentCapability.nodeIndex[fileId];
    const file: FileNode = {
      id: fileId,
      label: fileId.split('/').pop() || fileId,
      purpose: `${node.role} component in ${node.lane} layer`,
      lines: 0,
      role: node.role,
      lane: node.lane
    };
    setFocus(file);
    
    // Map nodeIndex path to actual file path
    // NodeIndex paths are like "src/app/utils/pg-api.util.ts"
    // But files.json paths are like "domain-locker/src/app/utils/pg-api.util.ts"
    const fullPath = `domain-locker/${fileId}`;
    
    // Load file content and summary
    await loadFileContent(fullPath);
  };

  const handleRunQuery = async (query: string) => {
    if (!repoId) return;
    
    setLoading(true);
    setQaResponse(null);
    
    try {
      const response = await apiClient.askQuestion(repoId, query);
      if (response.data) {
        setQaResponse(JSON.stringify(response.data, null, 2));
      } else if (response.error) {
        setQaResponse(`Error: ${response.error}`);
      }
    } catch (error) {
      console.error('Failed to process query:', error);
      setQaResponse(`Error: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  const isFolder = (n: any): n is FolderNode => (n as FolderNode).children !== undefined;

  // Load existing repository on mount
  useEffect(() => {
    const existingRepoId = 'repo_6d4eb310';
    setRepoId(existingRepoId);
    loadRepositoryData(existingRepoId);
  }, []);

  // Clear file content when changing focus to non-file items
  useEffect(() => {
    if (!focus || (focus as any).children) {
      setFileContent(null);
    }
  }, [focus]);

  // Show upload interface if no repository is loaded
  if (!repoId) {
    return (
      <div className="min-h-screen w-full bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 p-6 text-white">
        <div className="mx-auto max-w-4xl">
          <div className="mb-8 text-center">
            <div className="mb-4">
              <div className="rounded-2xl bg-white/10 px-4 py-2 font-semibold tracking-wide text-xl mx-auto w-fit backdrop-blur">
                Provis
              </div>
            </div>
            <p className="text-white/60 mb-8">Drop a repo. Understand. Fix. Add. Remove.</p>
          </div>
          <UploadInterface onComplete={handleUploadComplete} />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen w-full bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 p-6 text-white">
      <div className="mx-auto max-w-7xl space-y-6">
        {/* Header */}
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl bg-white/10 px-3 py-1.5 font-semibold tracking-wide backdrop-blur">Provis</div>
            <div className="hidden text-sm text-white/60 md:block">Drop a repo. Understand. Fix. Add. Remove.</div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                setRepoId(null);
                setCapabilities([]);
                setCurrentCapability(null);
                setSelectedCapability(null);
                setFocus(null);
                setFileContent(null);
                setQaResponse(null);
              }}
              className="flex items-center gap-2 rounded-lg bg-emerald-600/20 px-3 py-1.5 text-xs text-emerald-400 transition-colors hover:bg-emerald-600/30"
            >
              <Upload size={14} />
              New Repository
            </button>
            <div className="text-xs text-white/50">
              Repository {repoId} • {Object.keys(currentCapability?.nodeIndex || {}).length} files • {capabilities.length} capabilities
            </div>
          </div>
        </div>

        {/* Query bar */}
        <div className="mb-6 flex items-center gap-2">
          <div className="flex flex-1 items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 backdrop-blur">
            <Search size={16} className="text-white/60" />
            <input 
              value={query} 
              onChange={(e) => setQuery(e.target.value)} 
              onKeyDown={(e) => e.key === "Enter" && runQuery()} 
              placeholder="Ask anything: how does the deck render? fix images cut off? add speaker notes?" 
              className="w-full bg-transparent text-sm text-white placeholder:text-white/50 focus:outline-none" 
            />
            <button 
              onClick={runQuery} 
              disabled={loading || !query.trim()}
              className="rounded-xl bg-white/10 px-3 py-1.5 text-sm text-white hover:bg-white/15 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {loading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Processing...
                </>
              ) : (
                'Ask'
              )}
            </button>
            <button 
              onClick={() => setNovice(v => !v)} 
              className={`rounded-xl px-3 py-1.5 text-sm ${novice ? 'bg-emerald-400/20 text-emerald-200' : 'bg-white/10 text-white'} hover:bg-white/15`} 
              title="Show plain-English explanations and data flow"
            >
              {novice ? 'Novice mode: ON' : 'Novice mode: OFF'}
            </button>
          </div>
          <div className="hidden items-center gap-2 md:flex">
            <div className="inline-flex items-center gap-1">
              <PanelsTopLeft size={14} className="mr-1" /> 
              <span className="text-xs">{mode}</span>
            </div>
          </div>
        </div>

        {/* Starter & mode chips */}
        <div className="-mt-4 mb-4 flex flex-wrap gap-2 text-xs text-white/70">
          {['understand','fix','add','remove'].map(m => (
            <button 
              key={m} 
              onClick={() => setMode(m as any)} 
              className={`rounded-md px-2 py-0.5 ${mode===m ? 'bg-white/15' : 'bg-white/5'} hover:bg-white/10`}
            >
              {m}
            </button>
          ))}
          <span className="mx-2 opacity-50">•</span>
          {[
            {q: 'how does the deck render?', f: 'deck/compile.ts'},
            {q: 'fix images cut off', f: 'styles/print.css'},
            {q: 'where does data come from?', f: 'content/sections.ts'},
            {q: 'add speaker notes', f: 'templates/mdToHtml.ts'},
          ].map((s) => (
            <button 
              key={s.q} 
              onClick={() => { setQuery(s.q); }} 
              className="rounded-md bg-white/5 px-2 py-0.5 hover:bg-white/10"
            >
              {s.q}
            </button>
          ))}
        </div>

        <Legend />

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* Left column - Repository structure */}
          <div className="lg:col-span-4 space-y-6">
            {/* Repo structure */}
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white/90">
                <Folder size={16}/> Repository Structure
              </h2>
              {currentCapability ? (
                <FolderTree node={repoTree} onSelect={async (node) => {
                  const isFolder = (n: any): n is FolderNode => (n as FolderNode).children !== undefined;
                  if (!isFolder(node)) {
                    // It's a file - load its content
                    await handleFileSelect(node.id);
                  } else {
                    // It's a folder - just set focus
                    setFocus(node);
                    setFileContent(null);
                  }
                }} />
              ) : (
                <div className="text-center text-white/50 py-8">Loading repository structure...</div>
              )}
            </div>

            {/* Integrations and dependencies */}
            <div className="space-y-4">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white/90">
                  <Globe size={16}/> External Integrations
                </h2>
                <div className="flex flex-wrap gap-2 text-xs">
                  {integrations.length > 0 ? (
                    integrations.map(integration => (
                      <Badge key={integration}>{integration}</Badge>
                    ))
                  ) : (
                    <div className="text-white/50 text-xs">No external integrations detected</div>
                  )}
                </div>
              </div>

              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white/90">
                  <Package size={16}/> Dependencies
                </h2>
                <div className="flex flex-wrap gap-2 text-xs">
                  {dependencies.length > 0 ? (
                    dependencies.map(dep => (
                      <Badge key={dep}>{dep}</Badge>
                    ))
                  ) : (
                    <div className="text-white/50 text-xs">No dependencies detected</div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Middle column - Focused node */}
          <div className="lg:col-span-4">
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <div className="text-sm font-semibold text-white/90">
                Focus: {focus ? (isFolder(focus) ? focus.label : focus.label) : "Select a file or folder"}
              </div>
              <div className="mt-1 text-xs text-white/70">
                {focus ? focus.purpose : "Click on items in the repository structure to see details"}
              </div>
              {focus ? (
                <div className="mt-4">
                  {isFolder(focus) ? (
                    <div className="grid grid-cols-1 gap-2">
                      {focus.children?.map((c) => {
                        if (isFolder(c)) {
                          return (
                            <div key={c.id} className="rounded-lg border border-white/10 bg-white/5 p-2 text-xs text-white/70">
                              <Folder size={12} className="mb-1 text-white/80" />
                              <div className="font-medium text-white/90">{c.label}</div>
                              <div>{c.purpose}</div>
                            </div>
                          );
                        } else {
                          return (
                            <div key={c.id} className="cursor-pointer" onClick={() => handleFileSelect(c.id)}>
                              <FileBlock file={c} />
                            </div>
                          );
                        }
                      })}
                    </div>
                  ) : (
                    <FileDetails 
                      file={focus} 
                      fileContent={fileContent} 
                      loadingFile={loadingFile} 
                    />
                  )}
                </div>
              ) : (
                <div className="mt-4 text-center text-white/50 py-8">
                  Select a file or folder to see details
                </div>
              )}
            </div>
          </div>

          {/* Right column - Steps panel */}
          <div className="lg:col-span-4">
            <CapabilitySteps 
              capability={selectedCapability} 
              onFileSelect={async (fileId) => {
                await handleFileSelect(fileId);
              }}
              qaResponse={qaResponse}
              onRunQuery={handleRunQuery}
              loading={loading}
            />
          </div>
        </div>

        {/* Repo capabilities */}
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white/90">
            <GitBranch size={16}/> Capabilities
          </h2>
          {capabilities.length > 0 ? (
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
              {uiCapabilities.map((cap) => (
                <div
                  key={cap.id}
                  className={`rounded-lg border p-3 transition-all ${
                    selectedCapability?.id === cap.id
                      ? 'border-emerald-500/50 bg-emerald-500/10 shadow-lg shadow-emerald-500/10'
                      : 'border-white/10 bg-white/5 hover:border-white/20 hover:bg-white/10'
                  }`}
                >
                  <div 
                    className="cursor-pointer"
                    onClick={() => handleCapabilitySelect(cap)}
                  >
                    <div className="flex items-center gap-2">
                      <div className="font-medium text-white/90 text-sm">{cap.name}</div>
                      {selectedCapability?.id === cap.id && (
                        <div className="w-2 h-2 bg-emerald-400 rounded-full"></div>
                      )}
                    </div>
                    <div className="mt-1 text-xs text-white/70">{cap.desc}</div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      <Badge>entry: {cap.entryPoints.length}</Badge>
                      <Badge>files: {cap.keyFiles.length}</Badge>
                    </div>
                  </div>
                  <div className="mt-3 flex gap-2">
                    <button
                      onClick={() => handleCapabilityDashboard(cap.id)}
                      className="flex items-center gap-1 px-2 py-1 bg-emerald-600/20 text-emerald-200 rounded text-xs hover:bg-emerald-600/30 transition-colors"
                    >
                      <ExternalLink size={12} />
                      Dashboard
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center text-white/50 py-8">
              {loading ? (
                <div className="flex items-center justify-center gap-2">
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Loading capabilities...
                </div>
              ) : (
                'No capabilities found'
              )}
            </div>
          )}
        </div>

        {/* QA Response from main query */}
        {qaResponse && (
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-white/90">
            <SectionTitle icon={Search} title="Query Response" />
            <div className="mt-3 text-xs text-white/70">
              <pre className="whitespace-pre-wrap bg-black/20 p-3 rounded-lg overflow-auto max-h-60">
                {qaResponse}
              </pre>
            </div>
            <button 
              onClick={() => setQaResponse(null)} 
              className="mt-2 text-xs text-white/50 hover:text-white/80"
            >
              Clear response
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
