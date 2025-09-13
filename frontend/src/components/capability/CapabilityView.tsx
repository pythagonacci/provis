"use client";

import React, { useState, useMemo, useEffect } from 'react';
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
} from 'lucide-react';

import { Badge, Chip, SectionTitle } from '@/components/shared/ui';
import { SwimlaneFlow } from './SwimlaneFlow';
import { DataFlowBar } from './DataFlowBar';
import { NodeInspector } from './NodeInspector';
import { NarrativeSteps } from './NarrativeSteps';
import { PoliciesAndContracts } from './PoliciesAndContracts';
import { 
  FileNode, 
  FolderNode, 
  Capability, 
  TestResult, 
  Suggestion, 
  QueryMode, 
  Scope, 
  FunctionView 
} from '@/types/capability';
import { getPlaceholderData } from '@/lib/mock-data';

// This will be replaced with real data from the backend
const PLACEHOLDER_DATA = getPlaceholderData();

export function CapabilityView() {
  const [selectedFile, setSelectedFile] = useState<FileNode | null>(null);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<QueryMode>("understand");
  const [functionView, setFunctionView] = useState<FunctionView>('capabilities');
  const [selectedCapability, setSelectedCapability] = useState<Capability | null>(null);
  const [manualFocus, setManualFocus] = useState<string | null>(null);
  const [novice, setNovice] = useState<boolean>(true);
  const [highlighted, setHighlighted] = useState<string[]>([]);
  const [scope, setScope] = useState<Scope>('all');
  const [testResults, setTestResults] = useState<TestResult[]>(PLACEHOLDER_DATA.testResults);

  // TODO: Replace with real data from backend
  const files = PLACEHOLDER_DATA.files;
  const tree = PLACEHOLDER_DATA.tree;
  const capabilities = PLACEHOLDER_DATA.capabilities;

  // Query mode detection (will be enhanced with real AI)
  const detectMode = (q: string): QueryMode => {
    const lower = q.toLowerCase();
    if (/(fix|bug|issue|error)/.test(lower)) return "fix";
    if (/add|implement/.test(lower)) return "add";
    if (/remove|delete|deprecate/.test(lower)) return "remove";
    return "understand";
  };

  const runQuery = () => {
    setMode(detectMode(query));
    // TODO: Send query to backend and update state with results
  };

  // Focus file based on query or manual selection
  const focusFileId = useMemo(() => {
    if (manualFocus) return manualFocus;
    const q = query.toLowerCase();
    if (q.includes("outline")) return "slides/buildOutline.ts";
    if (q.includes("markdown") || q.includes("html")) return "templates/mdToHtml.ts";
    if (q.includes("print") || q.includes("css")) return "styles/print.css";
    if (q.includes("api")) return "pages/api/compileDeck.ts";
    return "deck/compile.ts";
  }, [query, manualFocus]);

  // Steps for selected capability or default
  const steps = useMemo(() => {
    if (selectedCapability) return selectedCapability.steps;
    return [
      { title: "Orchestrate deck build", description: "deck/compile.ts coordinates outline and rendering, then writes output", fileId: "deck/compile.ts" },
      { title: "Build slide outline", description: "slides/buildOutline.ts reads content/sections.ts to form structure", fileId: "slides/buildOutline.ts" },
      { title: "Render markdown to HTML", description: "templates/mdToHtml.ts converts markdown using markdown-it", fileId: "templates/mdToHtml.ts" },
      { title: "Serve via API", description: "pages/api/compileDeck.ts invokes compile() and returns HTML", fileId: "pages/api/compileDeck.ts" },
    ];
  }, [selectedCapability]);

  // Scoped tree based on selection
  const scopedTree = useMemo(() => {
    if (scope === 'all') return tree;
    const child = (tree.children as any[]).find((n) => (n as any).path === scope);
    return { id: 'root', path: '/', purpose: tree.purpose, children: child ? [child] : [] } as FolderNode;
  }, [scope, tree]);

  // Suggestions based on mode (will be replaced with real AI suggestions)
  const suggestions = useMemo((): Suggestion[] => {
    if (mode === "fix") {
      return [
        { fileId: "templates/mdToHtml.ts", rationale: "Handles image tags and layout; likely source of rendering glitches", confidence: "High" },
        { fileId: "styles/print.css", rationale: "Print margins/overflow may clip slides", confidence: "Med" },
        { fileId: "deck/compile.ts", rationale: "Orchestrates rendering; adjust pipeline or sanitization", confidence: "Med" },
      ];
    }
    if (mode === "add") {
      return [
        { fileId: "pages/api/compileDeck.ts", rationale: "Add endpoint parameter to support new deck variant", confidence: "High" },
        { fileId: "deck/compile.ts", rationale: "Insert branching to call new renderer", confidence: "High" },
        { fileId: "templates/mdToHtml.ts", rationale: "Implement renderer for new slide block type", confidence: "Med" },
      ];
    }
    if (mode === "remove") {
      return [
        { fileId: "slides/buildOutline.ts", rationale: "Removing an outline feature affects callers in compile.ts", confidence: "Med" },
        { fileId: "content/sections.ts", rationale: "Update section map to avoid dead references", confidence: "Med" },
      ];
    }
    return [
      { fileId: "deck/compile.ts", rationale: "Central orchestrator — start here to grasp the flow", confidence: "High" },
      { fileId: "slides/buildOutline.ts", rationale: "Explains the structure of slides", confidence: "High" },
    ];
  }, [mode]);

  // Tree item component
  const TreeItem = ({ node, onSelect }: { node: FolderNode | FileNode; onSelect: (n: any) => void }) => {
    const isFolder = (n: any): n is FolderNode => (n as FolderNode).children !== undefined;
    const [open, setOpen] = useState(true);

    if (isFolder(node)) {
      return (
        <div className="mb-1">
          <button
            onClick={() => setOpen((v) => !v)}
            className="group flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left hover:bg-white/5"
          >
            <div className="flex items-center gap-2">
              <FolderIcon size={16} className="text-white/80" />
              <div>
                <div className="text-sm text-white/90">{node.path}</div>
                <div className="text-xs text-white/50">{node.purpose}</div>
              </div>
            </div>
            <ChevronDown size={16} className={`transition-transform ${open ? "rotate-0" : "-rotate-90"} text-white/60`} />
          </button>
          <AnimatePresence initial={false}>
            {open && (
              <motion.div 
                initial={{ height: 0, opacity: 0 }} 
                animate={{ height: "auto", opacity: 1 }} 
                exit={{ height: 0, opacity: 0 }} 
                className="ml-5 border-l border-white/10 pl-3"
              >
                {(node.children as any[]).map((child) => (
                  <TreeItem key={(child as any).id} node={child} onSelect={onSelect} />
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      );
    }

    return (
      <button 
        onClick={() => onSelect(node)} 
        className="group flex w-full items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-white/5"
      >
        <FileIcon size={16} className="text-white/70" />
        <div>
          <div className="text-sm text-white/90">{node.path}</div>
          <div className="text-xs text-white/50">{node.purpose}</div>
        </div>
      </button>
    );
  };

  // Legend component
  const Legend = () => (
    <div className="mb-4 rounded-2xl border border-white/10 bg-white/5 p-3 text-white/90">
      <SectionTitle icon={PanelsTopLeft} title="Legend" />
      <div className="mt-2 grid grid-cols-1 gap-3 text-xs md:grid-cols-2">
        <div>
          <div className="mb-1 font-medium text-white/80">Side-effects badges</div>
          <div className="flex flex-wrap gap-2">
            <Badge>io</Badge> <span className="text-white/60">filesystem / streams</span>
          </div>
          <div className="mt-1 flex flex-wrap gap-2">
            <Badge>net</Badge> <span className="text-white/60">HTTP / fetch / sockets</span>
          </div>
          <div className="mt-1 flex flex-wrap gap-2">
            <Badge>db</Badge> <span className="text-white/60">database queries</span>
          </div>
          <div className="mt-1 flex flex-wrap gap-2">
            <Badge>dom</Badge> <span className="text-white/60">DOM mutations</span>
          </div>
          <div className="mt-1 flex flex-wrap gap-2">
            <Badge>render</Badge> <span className="text-white/60">HTML/JSX/SSR output</span>
          </div>
        </div>
        <div>
          <div className="mb-1 font-medium text-white/80">Role badges</div>
          <div className="flex flex-wrap gap-2">
            <Badge>Entry point</Badge> <span className="text-white/60">receives request / starts flow</span>
          </div>
          <div className="mt-1 flex flex-wrap gap-2">
            <Badge>Orchestrator</Badge> <span className="text-white/60">coordinates other modules</span>
          </div>
          <div className="mt-1 flex flex-wrap gap-2">
            <Badge>Source</Badge> <span className="text-white/60">reads data / config</span>
          </div>
          <div className="mt-1 flex flex-wrap gap-2">
            <Badge>Sink</Badge> <span className="text-white/60">writes output / responds</span>
          </div>
          <div className="mt-1 flex flex-wrap gap-2">
            <Badge>Key file</Badge> <span className="text-white/60">high-impact edit target</span>
          </div>
        </div>
      </div>
    </div>
  );

  // Capability card component
  const CapabilityCard = ({ cap, onFocus, onSelect }: { cap: Capability; onFocus: () => void; onSelect: () => void }) => (
    <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-white/90">
      <div className="mb-1 text-sm font-semibold">{cap.name}</div>
      <div className="mb-2 text-xs text-white/70">{cap.purpose}</div>
      <div className="mb-2 flex flex-wrap gap-2 text-xs">
        <Badge>entry: {cap.entryPoints.length}</Badge>
        <Badge>orchestrators: {cap.orchestrators.length}</Badge>
        <Badge>sources: {cap.sources.length}</Badge>
        <Badge>sinks: {cap.sinks.length}</Badge>
      </div>
      <div className="text-xs text-white/60">
        Data in: {cap.dataIn.join(', ')}<br/>
        Data out: {cap.dataOut.join(', ')}
      </div>
      <div className="mt-3 flex gap-2">
        <button 
          onClick={onFocus} 
          className="rounded-md bg-white/10 px-2 py-1 text-xs hover:bg-white/15"
        >
          Focus in graph
        </button>
        <button 
          onClick={onSelect} 
          className="rounded-md bg-white/10 px-2 py-1 text-xs hover:bg-white/15"
        >
          Show steps
        </button>
      </div>
    </div>
  );

  // Tests panel component
  const TestsPanel = ({ results }: { results: TestResult[] }) => {
    const allPass = results.every((r) => r.pass);
    return (
      <div className="mt-6 rounded-2xl border border-white/10 bg-white/5 p-3 text-white/90">
        <SectionTitle icon={PanelsTopLeft} title="System Status" />
        <div className="mt-2 text-xs text-white/70">
          {allPass ? "All systems operational" : "Some systems pending (see below)"}
        </div>
        <ul className="mt-2 space-y-1 text-xs">
          {results.map((r, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className={`mt-0.5 inline-flex h-4 w-4 items-center justify-center rounded ${r.pass ? 'bg-emerald-500/30' : 'bg-rose-500/30'}`}>
                {r.pass ? '✓' : '!'}
              </span>
              <div>
                <div className="font-medium">{r.name}</div>
                {r.details && <div className="text-white/60">{r.details}</div>}
              </div>
            </li>
          ))}
        </ul>
      </div>
    );
  };

  return (
    <div className="min-h-[720px] w-full bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 p-6 text-white">
      {/* Header */}
      <div className="mx-auto max-w-6xl">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl bg-white/10 px-3 py-1.5 font-semibold tracking-wide backdrop-blur">
              Provis
            </div>
            <div className="hidden text-sm text-white/60 md:block">
              Drop a repo. Understand. Fix. Add. Remove.
            </div>
          </div>
          <div className="text-xs text-white/50">
            Parsed {Object.keys(files).length} files • {Object.values(files).reduce((acc, f) => acc + f.imports.length, 0)} imports • 0.6s
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
              className="rounded-xl bg-white/10 px-3 py-1.5 text-sm text-white hover:bg-white/15"
            >
              Ask
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
              onClick={() => setMode(m as QueryMode)} 
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
              onClick={() => { setQuery(s.q); setManualFocus(s.f); }} 
              className="rounded-md bg-white/5 px-2 py-0.5 hover:bg-white/10"
            >
              {s.q}
            </button>
          ))}
        </div>

        <Legend />

        {/* Main grid */}
        <div className="grid grid-cols-1 gap-6 md:grid-cols-12">
          {/* Left: Folder map */}
          <div className="md:col-span-4">
            <div className="rounded-2xl border border-white/10 bg-white/5 p-3 backdrop-blur">
              <SectionTitle icon={FolderIcon} title="Folder map" />
              <div className="mt-3 max-h-[420px] overflow-auto pr-2">
                <div className="mb-2 flex flex-wrap gap-2 text-xs">
                  {['all','app','pages','deck','slides','templates','content','styles'].map((s) => (
                    <button 
                      key={s} 
                      onClick={() => setScope(s as Scope)} 
                      className={`rounded-md px-2 py-0.5 ${scope===s ? 'bg-white/15' : 'bg-white/5'} hover:bg-white/10`}
                    >
                      {s}
                    </button>
                  ))}
                </div>
                <TreeItem node={scopedTree} onSelect={(n) => setSelectedFile(n as FileNode)} />
              </div>
            </div>
          </div>

          {/* Center: Flow graph */}
          <div className="md:col-span-4">
            <SectionTitle icon={GitBranch} title="Focused flow" />
            <div className="mt-3">
              <DataFlowBar capability={selectedCapability} />
              <SwimlaneFlow 
                focus={focusFileId} 
                highlighted={highlighted} 
                onSelect={(id) => { 
                  const f = (files as any)[id]; 
                  if (f) setSelectedFile(f); 
                  setManualFocus(id); 
                }} 
              />
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-white/70">
                <Chip>Group by folder</Chip>
                <Chip>Hide externals</Chip>
                <Chip>Focus mode</Chip>
              </div>
            </div>
          </div>

          {/* Right: Details */}
          <div className="md:col-span-4">
            <div className="space-y-3">
              <NodeInspector 
                file={selectedFile} 
                selectedCapability={selectedCapability} 
                novice={novice} 
              />
              <NarrativeSteps 
                steps={steps} 
                onHover={(fid) => setHighlighted(fid ? [fid] : [])} 
                onSelect={(fid) => { 
                  if (!fid) return; 
                  const f = (files as any)[fid]; 
                  if (f) setSelectedFile(f); 
                  setManualFocus(fid); 
                }} 
              />
              <PoliciesAndContracts 
                suggestions={suggestions} 
                onSelect={(fid) => { 
                  const f = (files as any)[fid]; 
                  if (f) setSelectedFile(f); 
                  setManualFocus(fid); 
                }} 
              />
            </div>
          </div>
        </div>

        {/* Functions & Capabilities */}
        <div className="mt-6 rounded-2xl border border-white/10 bg-white/5 p-4">
          <SectionTitle icon={ListTree} title="Functions & Capabilities" />
          <div className="mt-3">
            {/* Toggle */}
            <div className="mb-3 inline-flex overflow-hidden rounded-xl border border-white/10 text-xs">
              <button 
                onClick={() => setFunctionView('capabilities')} 
                className={`px-3 py-1.5 ${functionView==='capabilities' ? 'bg-white/15' : 'bg-white/5'}`}
              >
                Capabilities
              </button>
              <button 
                onClick={() => setFunctionView('code')} 
                className={`px-3 py-1.5 ${functionView==='code' ? 'bg-white/15' : 'bg-white/5'}`}
              >
                Code functions
              </button>
            </div>

            {functionView === 'capabilities' ? (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
                {capabilities.map((cap) => (
                  <CapabilityCard 
                    key={cap.id} 
                    cap={cap} 
                    onFocus={() => setManualFocus(cap.orchestrators[0]?.split('#')[0] || cap.keyFiles[0])} 
                    onSelect={() => setSelectedCapability(cap)} 
                  />
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
                {Object.values(files).flatMap((f) => f.functions.map((fn) => ({ fn, file: f }))).map(({ fn, file }) => (
                  <div key={fn.id} className="rounded-xl border border-white/10 bg-white/5 p-3">
                    <div className="mb-1 text-sm font-medium">
                      {fn.name} <span className="text-white/50">in</span> {file.path}
                    </div>
                    <div className="text-xs text-white/70">{fn.summary}</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {fn.sideEffects.map((s) => (<Badge key={s}>{s}</Badge>))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* System Status */}
        <TestsPanel results={testResults} />
      </div>
    </div>
  );
}
