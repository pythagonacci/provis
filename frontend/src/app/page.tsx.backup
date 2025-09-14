'use client';

import { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Folder as FolderIcon, 
  File as FileIcon, 
  Search, 
  GitBranch, 
  PanelsTopLeft, 
  ListTree, 
  Wand2, 
  ChevronDown, 
  Database, 
  Server, 
  Globe, 
  Activity,
  Upload,
  RefreshCw
} from 'lucide-react';
import { apiClient, CapabilityDetail, CapabilitySummary } from '@/lib/api';
import FlowGraph from '@/components/FlowGraph';
import LayerGroup from '@/components/LayerGroup';
import DataFlowBar from '@/components/DataFlowBar';
import Steps from '@/components/Steps';
import Suggest from '@/components/Suggest';
import ModuleCard from '@/components/ModuleCard';
import API from '@/components/API';
import Models from '@/components/Models';
import { Badge } from '@/components/shared/Badge';
import { Chip } from '@/components/shared/Chip';
import { Title } from '@/components/shared/Title';




// Types
type SE = "io" | "net" | "db" | "dom" | "render";
type Func = {
  id: string;
  name: string;
  summary: string;
  sideEffects: SE[];
  callers?: string[];
  callees?: string[];
};
type Module = {
  id: string;
  path: string;
  purpose: string;
  exports: string[];
  imports: string[];
  functions: Func[];
  layer: "ui" | "api" | "service" | "data" | "shared";
};
type Endpoint = {
  id: string;
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  path: string;
  handlerFile: string;
  request?: {
    params?: string[];
    query?: string[];
    body?: string;
  };
  response?: {
    type?: string;
    fields?: string[];
  };
};
type Model = {
  id: string;
  engine: "prisma" | "mongoose" | "sequelize" | "sql" | "zod" | "custom";
  file: string;
  fields: {
    name: string;
    type: string;
    optional?: boolean;
    relation?: string;
  }[];
};
type Capability = {
  id: string;
  name: string;
  purpose: string;
  entryPoints: string[];
  orchestrators: string[];
  sources: string[];
  sinks: string[];
  dataIn: string[];
  dataOut: string[];
  keyFiles: string[];
  steps: {
    title: string;
    description: string;
    fileId?: string;
  }[];
};
type RepoScan = {
  summary: {
    files: number;
    modules: number;
    endpoints: number;
    models: number;
    jobs: number;
    packages: number;
    lines?: number;
    lastIndexed: string;
  };
  modules: Record<string, Module>;
  endpoints: Endpoint[];
  models: Model[];
  packages: {
    name: string;
    version: string;
    kind: "prod" | "dev";
  }[];
  scripts: {
    name: string;
    cmd: string;
  }[];
  jobs: {
    id: string;
    kind: "cron" | "queue" | "worker";
    schedule?: string;
    file: string;
    description: string;
  }[];
  capabilities: Capability[];
};




// Upload Interface
const UploadInterface = ({ onUploadComplete }: { onUploadComplete: (repoId: string) => void }) => {
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'processing' | 'complete' | 'error'>('idle');
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [repoId, setRepoId] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState('');

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

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
      const uploadResponse = await apiClient.ingestRepository(file);
      
      if (uploadResponse.error) {
        throw new Error(uploadResponse.error);
      }

      const { repoId: newRepoId, jobId } = uploadResponse.data;
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

        const status = statusResponse.data;
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
          onUploadComplete(status.repoId);
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
    }, 2000);
  };

  const getStatusIcon = () => {
    switch (uploadStatus) {
      case 'uploading':
      case 'processing':
        return <RefreshCw className="w-6 h-6 animate-spin text-emerald-400" />;
      case 'complete':
        return <div className="w-6 h-6 rounded-full bg-emerald-500 flex items-center justify-center">✓</div>;
      case 'error':
        return <div className="w-6 h-6 rounded-full bg-red-500 flex items-center justify-center">!</div>;
      default:
        return <Upload className="w-6 h-6 text-white/60" />;
    }
  };

  if (uploadStatus === 'complete') {
    return (
      <div className="text-center py-12">
        <div className="w-16 h-16 bg-emerald-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
          <div className="w-8 h-8 bg-emerald-500 rounded-full flex items-center justify-center text-white font-bold">✓</div>
        </div>
        <h2 className="text-2xl font-bold text-white mb-2">Repository Ready!</h2>
        <p className="text-white/70 mb-6">Repository {repoId} has been analyzed and is ready for exploration.</p>
        <button
          onClick={() => {
            setUploadStatus('idle');
            setRepoId(null);
            setProgress(0);
            setStatusMessage('');
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
        {uploadStatus === 'idle' && 'Drop a Repository'}
        {uploadStatus === 'uploading' && 'Uploading Repository'}
        {uploadStatus === 'processing' && 'Analyzing Codebase'}
        {uploadStatus === 'error' && 'Upload Failed'}
      </h2>
      
      <p className="text-white/70 mb-8 max-w-md mx-auto">
        {uploadStatus === 'idle' && 'Upload a ZIP file to analyze your repository\'s architecture, API endpoints, data models, and capabilities.'}
        {uploadStatus === 'uploading' && 'Uploading your repository files...'}
        {uploadStatus === 'processing' && statusMessage}
        {uploadStatus === 'error' && uploadError}
      </p>

      {uploadStatus === 'idle' && (
        <label className="cursor-pointer">
          <input
            type="file"
            accept=".zip"
            onChange={handleFileUpload}
            className="hidden"
            disabled={uploading}
          />
          <div className="inline-flex items-center px-6 py-3 bg-emerald-500/20 text-emerald-200 rounded-xl hover:bg-emerald-500/30 transition-colors border border-emerald-500/30">
            <Upload className="w-5 h-5 mr-2" />
            Choose Repository ZIP File
          </div>
        </label>
      )}

      {uploadStatus === 'processing' && (
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
    </div>
  );
};

// Legend
const Legend = () => (
  <div className="mb-4 rounded-2xl border border-white/10 bg-white/5 p-3 text-white/90">
    <Title icon={PanelsTopLeft} title="Legend" />
    <div className="mt-2 grid grid-cols-1 gap-3 text-xs md:grid-cols-3">
      <div>
        <div className="mb-1 font-medium text-white/80">Effects</div>
        <div className="flex flex-wrap gap-2">
          <Badge>io</Badge>
          <Badge>net</Badge>
          <Badge>db</Badge>
          <Badge>dom</Badge>
          <Badge>render</Badge>
        </div>
      </div>
      <div>
        <div className="mb-1 font-medium text-white/80">Layers</div>
        <div className="flex flex-wrap gap-2">
          <Badge>UI</Badge>
          <Badge>API</Badge>
          <Badge>Service</Badge>
          <Badge>Data</Badge>
          <Badge>Shared</Badge>
        </div>
      </div>
      <div>
        <div className="mb-1 font-medium text-white/80">Roles</div>
        <div className="flex flex-wrap gap-2">
          <Badge>Entry</Badge>
          <Badge>Orchestrator</Badge>
          <Badge>Source</Badge>
          <Badge>Sink</Badge>
          <Badge>Key</Badge>
        </div>
      </div>
    </div>
  </div>
);

export default function ProvisRepoMap() {
  const [scan, setScan] = useState<RepoScan | null>(null);
  const [mod, setMod] = useState<Module | null>(null);
  const [cap, setCap] = useState<Capability | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  const [hi, setHi] = useState<string[]>([]);
  const [nov, setNov] = useState(true);
  const [mode, setMode] = useState<"understand" | "fix" | "add" | "remove">("understand");
  const [q, setQ] = useState("");
  const [repoId, setRepoId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const handleUploadComplete = async (newRepoId: string) => {
    setRepoId(newRepoId);
    await loadRepositoryData(newRepoId);
  };

  const loadRepositoryData = async (id: string) => {
    try {
      // Load capabilities first
      const capabilitiesResponse = await apiClient.getCapabilities(id);
      if (capabilitiesResponse.data && capabilitiesResponse.data.length > 0) {
        const capability = capabilitiesResponse.data[0];
        setCap({
          id: capability.id,
          name: capability.name,
          purpose: capability.purpose,
          entryPoints: capability.entryPoints,
          orchestrators: capability.orchestrators || [],
          sources: capability.sources,
          sinks: capability.sinks,
          dataIn: capability.dataIn,
          dataOut: capability.dataOut,
          keyFiles: capability.keyFiles,
          steps: [] // Will be loaded from detail API
        });
      }

      // Load detailed capability data
      const detailResponse = await apiClient.getCapability(id, 'cap_main_workflow');
      if (detailResponse.data) {
        const detail = detailResponse.data;
        setCap({
          id: detail.id,
          name: detail.name,
          purpose: detail.purpose,
          entryPoints: detail.entryPoints,
          orchestrators: detail.orchestrators,
          sources: detail.sources,
          sinks: detail.sinks,
          dataIn: detail.dataIn,
          dataOut: detail.dataOut,
          keyFiles: detail.keyFiles,
          steps: detail.steps
        });

        // Convert to RepoScan format
        const mockScan: RepoScan = {
          summary: {
            files: Object.keys(detail.nodeIndex).length,
            modules: Object.keys(detail.nodeIndex).length,
            endpoints: detail.entryPoints.length,
            models: detail.dataFlow.stores.length,
            jobs: 0,
            packages: detail.dataFlow.externals.length,
            lines: 0,
            lastIndexed: new Date().toISOString()
          },
          modules: Object.entries(detail.nodeIndex).reduce((acc, [path, node]) => {
            acc[path] = {
              id: path,
              path: path,
              purpose: `${node.role} component`,
              exports: [],
              imports: [],
              functions: [],
              layer: node.lane as Module["layer"]
            };
            return acc;
          }, {} as Record<string, Module>),
          endpoints: detail.entryPoints.map((ep, index) => ({
            id: `endpoint-${index}`,
            method: 'GET' as const,
            path: ep,
            handlerFile: ep
          })),
          models: detail.dataFlow.stores.map((store, index) => ({
            id: store.name,
            engine: 'custom' as const,
            file: store.path || '',
            fields: store.fields || []
          })),
          packages: detail.dataFlow.externals.map((ext, index) => ({
            name: ext.name,
            version: '1.0.0',
            kind: 'prod' as const
          })),
          scripts: [],
          jobs: [],
          capabilities: [{
            id: detail.id,
            name: detail.name,
            purpose: detail.purpose,
            entryPoints: detail.entryPoints,
            orchestrators: detail.orchestrators,
            sources: detail.sources,
            sinks: detail.sinks,
            dataIn: detail.dataIn,
            dataOut: detail.dataOut,
            keyFiles: detail.keyFiles,
            steps: detail.steps
          }]
        };

        setScan(mockScan);
      }
    } catch (error) {
      console.error('Failed to load repository data:', error);
    }
  };

  const metrics = useMemo(() => {
    if (!scan) return '';
    const s = scan.summary;
    return `${s.files} files • ${s.modules} modules • ${s.endpoints} endpoints • ${s.models} models • ${s.jobs} jobs`;
  }, [scan?.summary]);

  const focusId = useMemo(() => {
    if (!scan) return null;
    if (focus) return focus;
    const l = q.toLowerCase();
    if (l.includes("api")) return scan.endpoints[0] ? `endpoint:${scan.endpoints[0].method} ${scan.endpoints[0].path}` : Object.keys(scan.modules)[0];
    if (l.includes("model") || l.includes("schema")) return `model:${scan.models[0]?.id}`;
    return scan.capabilities[0]?.orchestrators[0]?.split('#')[0] || Object.keys(scan.modules)[0];
  }, [q, focus, scan]);

  const steps = useMemo(() => cap ? cap.steps : (scan?.capabilities[0]?.steps || []), [cap, scan]);

  const suggestions = useMemo(() => {
    if (!scan) return [];
    if (mode === "fix") return [
      { fileId: "main.py", rationale: "Main entry point - check for error handling", confidence: "High" as const },
      { fileId: "app.py", rationale: "Application logic - validate data flow", confidence: "Med" as const }
    ];
    if (mode === "add") return [
      { fileId: "routes/", rationale: "Add new API endpoints here", confidence: "High" as const },
      { fileId: "models/", rationale: "Define new data models", confidence: "Med" as const }
    ];
    return [
      { fileId: "README.md", rationale: "Start here to understand the project", confidence: "High" as const },
      { fileId: "main.py", rationale: "Application entry point", confidence: "High" as const }
    ];
  }, [mode, scan]);

  const hits = useMemo(() => {
    if (!scan) return [];
    const x = q.trim().toLowerCase();
    if (!x) return [];
    
    const m = Object.values(scan.modules).filter(v => 
      v.path.toLowerCase().includes(x) || v.purpose.toLowerCase().includes(x)
    ).map(v => ({ kind: "module", id: v.id, label: v.path }));
    
    const e = scan.endpoints.filter(v => 
      v.path.toLowerCase().includes(x) || v.method.toLowerCase().includes(x)
    ).map(v => ({ kind: "endpoint", id: `endpoint:${v.method} ${v.path}`, label: `${v.method} ${v.path}` }));
    
    const d = scan.models.filter(v => v.id.toLowerCase().includes(x)).map(v => ({ 
      kind: "model", 
      id: `model:${v.id}`, 
      label: v.id 
    }));
    
    const c = scan.capabilities.filter(v => 
      v.name.toLowerCase().includes(x) || v.purpose.toLowerCase().includes(x)
    ).map(v => ({ kind: "cap", id: v.id, label: v.name }));
    
    return [...m, ...e, ...d, ...c].slice(0, 8);
  }, [q, scan]);

  if (!scan) {
    return (
      <div className="min-h-screen w-full bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 p-6 text-white">
        <div className="mx-auto max-w-4xl">
          <div className="mb-8 text-center">
            <div className="mb-4">
              <div className="rounded-2xl bg-white/10 px-4 py-2 font-semibold tracking-wide text-xl mx-auto w-fit backdrop-blur">
                Provis
              </div>
            </div>
            <p className="text-white/60 mb-8">Drop a repo. Architecture, API, models, and capabilities.</p>
          </div>
          <UploadInterface onUploadComplete={handleUploadComplete} />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen w-full bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 p-6 text-white">
      <div className="mx-auto max-w-7xl">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl bg-white/10 px-3 py-1.5 font-semibold tracking-wide backdrop-blur">
              Provis
            </div>
            <div className="hidden text-sm text-white/60 md:block">
              Architecture, API, models, and capabilities.
            </div>
          </div>
          <div className="text-xs text-white/50">
            {scan.summary.files} files • {scan.summary.modules} modules • {scan.summary.endpoints} endpoints • {scan.summary.models} models • {scan.summary.jobs} jobs • indexed {new Date(scan.summary.lastIndexed).toLocaleString()}
          </div>
        </div>

        <div className="mb-6 flex items-center gap-2">
          <div className="flex flex-1 items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-3 py-2">
            <Search size={16} className="text-white/60" />
            <input 
              value={q} 
              onChange={e => setQ(e.target.value)} 
              placeholder="Search or ask: where are the APIs?" 
              className="w-full bg-transparent text-sm text-white placeholder:text-white/50 focus:outline-none"
            />
            <button 
              onClick={() => setNov(v => !v)} 
              className={`rounded-xl px-3 py-1.5 text-sm ${nov ? 'bg-emerald-400/20 text-emerald-200' : 'bg-white/10 text-white'}`}
            >
              {nov ? 'Novice: ON' : 'Novice: OFF'}
            </button>
          </div>
          <div className="hidden items-center gap-2 md:flex text-xs">
            {["understand", "fix", "add", "remove"].map(m => (
              <button 
                key={m} 
                onClick={() => setMode(m as any)} 
                className={`rounded-md px-2 py-0.5 ${mode === m ? 'bg-white/15' : 'bg-white/5'} hover:bg-white/10`}
              >
                {m}
              </button>
            ))}
          </div>
        </div>

        <Legend />
        
        <div className="grid grid-cols-1 gap-6 md:grid-cols-12">
          <div className="md:col-span-4">
            <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
              <Title icon={FolderIcon} title="Modules by layer" />
              <div className="mt-2 max-h-[420px] overflow-auto pr-2 text-sm">
                {["ui", "api", "service", "data", "shared"].map(layer => (
                  <LayerGroup 
                    key={layer} 
                    layer={layer as Module["layer"]} 
                    modules={Object.values(scan.modules).filter(m => m.layer === layer)} 
                    onSelect={m => {
                      setMod(m);
                      setFocus(m.id);
                    }}
                  />
                ))}
              </div>
            </div>
          </div>
          
          <div className="md:col-span-4">
            <Title icon={GitBranch} title="Architecture map" />
            <div className="mt-3">
              <DataFlowBar cap={cap} />
              <FlowGraph 
                scan={scan} 
                focus={focusId} 
                hi={hi} 
                onSelect={id => {
                  if (id.startsWith("endpoint:")) {
                    setCap(scan.capabilities[0] || null);
                    setFocus(id);
                    return;
                  }
                  const m = scan.modules[id];
                  if (m) {
                    setMod(m);
                    setFocus(id);
                  }
                }}
              />
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-white/70">
                <Chip>Lane view</Chip>
                <Chip>Hide externals</Chip>
                <Chip>Focus</Chip>
              </div>
            </div>
          </div>
          
          <div className="md:col-span-4">
            <div className="space-y-3">
              {mod ? (
                <ModuleCard m={mod} cap={cap} nov={nov} />
              ) : (
                <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-center text-white/70">
                  Select a node to see details.
                </div>
              )}
              <Steps 
                steps={steps} 
                onHover={id => setHi(id ? [id] : [])} 
                onSelect={id => {
                  if (!id) return;
                  const m = scan.modules[id];
                  if (m) setMod(m);
                  setFocus(id || null);
                }}
              />
              <Suggest 
                items={suggestions} 
                onSelect={id => {
                  const m = scan.modules[id];
                  if (m) setMod(m);
                  setFocus(id);
                }}
              />
            </div>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-12">
          <div className="md:col-span-6">
            <API eps={scan.endpoints} onSelect={fid => {
              const f = scan.modules[fid];
              if (f) setMod(f);
              setFocus(fid);
            }} />
          </div>
          <div className="md:col-span-6">
            <Models models={scan.models} onSelect={fid => {
              const f = scan.modules[fid];
              if (f) setMod(f);
              setFocus(fid);
            }} />
          </div>
        </div>
      </div>
    </div>
  );
}
