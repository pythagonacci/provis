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

// UI Components
const Badge = ({ children }: { children: React.ReactNode }) => (
  <span className="inline-flex items-center rounded-full border border-white/15 bg-white/5 px-2.5 py-0.5 text-xs text-white/80 backdrop-blur">
    {children}
  </span>
);

const Chip = ({ children }: { children: React.ReactNode }) => (
  <span className="inline-flex items-center rounded-md bg-white/10 px-2 py-0.5 text-xs text-white/80">
    {children}
  </span>
);

const Title = ({ icon: Icon, title }: { icon: any; title: string }) => (
  <div className="flex items-center gap-2 text-white/90">
    <Icon size={16} className="opacity-80" />
    <h3 className="text-sm font-medium tracking-wide">{title}</h3>
  </div>
);

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
          <div className="text-center py-12">
            <div className="w-16 h-16 bg-white/10 rounded-full flex items-center justify-center mx-auto mb-6">
              <Upload className="w-6 h-6 text-white/60" />
            </div>
            <h2 className="text-2xl font-bold text-white mb-2">Drop a Repository</h2>
            <p className="text-white/70 mb-8 max-w-md mx-auto">
              Upload a ZIP file to analyze your repository's architecture, API endpoints, data models, and capabilities.
            </p>
            <div className="inline-flex items-center px-6 py-3 bg-emerald-500/20 text-emerald-200 rounded-xl border border-emerald-500/30">
              <Upload className="w-5 h-5 mr-2" />
              Choose Repository ZIP File
            </div>
          </div>
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
                <div className="text-white/70 text-center py-8">Repository analysis will appear here</div>
              </div>
            </div>
          </div>
          
          <div className="md:col-span-4">
            <Title icon={GitBranch} title="Architecture map" />
            <div className="mt-3">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-8 text-center text-white/70">
                Architecture visualization will appear here
              </div>
            </div>
          </div>
          
          <div className="md:col-span-4">
            <div className="space-y-3">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-center text-white/70">
                Select a node to see details.
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-center text-white/70">
                Steps will appear here
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-center text-white/70">
                Suggestions will appear here
              </div>
            </div>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-12">
          <div className="md:col-span-6">
            <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-center text-white/70">
              API endpoints will appear here
            </div>
          </div>
          <div className="md:col-span-6">
            <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-center text-white/70">
              Data models will appear here
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
