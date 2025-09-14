"use client";

import React, { useMemo, useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Folder as FolderIcon,
  File as FileIcon,
  Search,
  GitBranch,
  PanelsTopLeft,
  ListTree,
  Wand2,
  ChevronDown,
  Upload,
  RefreshCw,
  AlertCircle,
  CheckCircle,
} from "lucide-react";
import { apiClient, CapabilitySummary, CapabilityDetail } from "@/lib/api";

/**
 * Provis — Visual Frontend Demo (v2)
 * Upgrades: clickable graph, hover highlights, folder scope chips, starter chips,
 * novice mode, capability data-flow bar, role badges, and interactive steps/suggestions.
 */

/** -----------------------------
 * Mock repo data (JS/TS example)
 * ------------------------------*/

type Func = {
  id: string;
  name: string;
  summary: string;
  sideEffects: ("io" | "net" | "db" | "dom" | "render")[];
  callers?: string[]; // function ids
  callees?: string[]; // function ids
};

type FileNode = {
  id: string;
  path: string;
  purpose: string;
  exports: string[];
  imports: string[]; // file ids
  functions: Func[];
};

type FolderNode = {
  id: string;
  path: string;
  purpose: string;
  children: (FolderNode | FileNode)[];
};

// High-level capability = end-to-end functionality (e.g., "Compile slide deck")
type Capability = {
  id: string;
  name: string;
  purpose: string;
  entryPoints: string[]; // files/routes that start the flow
  orchestrators: string[]; // main symbols controlling the flow
  sources: string[]; // data sources (files/schemas)
  sinks: string[]; // outputs (responses/files/db)
  dataIn: string[]; // params, schemas, request bodies (names only)
  dataOut: string[]; // returns, side effects (names only)
  keyFiles: string[]; // important files for editing
  steps: { title: string; description: string; fileId?: string }[];
};

const MOCK_FILES: Record<string, FileNode> = {
  "app/page.tsx": {
    id: "app/page.tsx",
    path: "app/page.tsx",
    purpose: "Route entry (UI) — allows compiling a deck and viewing output",
    exports: ["Page"],
    imports: ["pages/api/compileDeck.ts"],
    functions: [
      {
        id: "app/page.tsx#Page",
        name: "Page",
        summary: "Renders UI and triggers deck compilation via API",
        sideEffects: ["render", "net"],
      },
    ],
  },
  "pages/api/compileDeck.ts": {
    id: "pages/api/compileDeck.ts",
    path: "pages/api/compileDeck.ts",
    purpose: "API route that calls the orchestrator and returns HTML",
    exports: ["handler"],
    imports: ["deck/compile.ts"],
    functions: [
      {
        id: "pages/api/compileDeck.ts#handler",
        name: "handler",
        summary: "Receives request, calls compile, returns deck HTML",
        sideEffects: ["net", "io"],
        callees: ["deck/compile.ts#compile"],
      },
    ],
  },
  "deck/compile.ts": {
    id: "deck/compile.ts",
    path: "deck/compile.ts",
    purpose: "Orchestrates deck creation: outline -> markdown -> HTML -> output",
    exports: ["compile"],
    imports: ["slides/buildOutline.ts", "templates/mdToHtml.ts", "styles/print.css"],
    functions: [
      {
        id: "deck/compile.ts#compile",
        name: "compile",
        summary: "Coordinates outline building and slide rendering, writes final HTML",
        sideEffects: ["io"],
        callees: [
          "slides/buildOutline.ts#buildOutline",
          "templates/mdToHtml.ts#mdToHtml",
        ],
      },
    ],
  },
  "slides/buildOutline.ts": {
    id: "slides/buildOutline.ts",
    path: "slides/buildOutline.ts",
    purpose: "Aggregates sections with metadata into a slide outline",
    exports: ["buildOutline"],
    imports: ["content/sections.ts"],
    functions: [
      {
        id: "slides/buildOutline.ts#buildOutline",
        name: "buildOutline",
        summary: "Reads section definitions and forms the slide structure",
        sideEffects: [],
        callees: ["content/sections.ts#getSections"],
      },
    ],
  },
  "templates/mdToHtml.ts": {
    id: "templates/mdToHtml.ts",
    path: "templates/mdToHtml.ts",
    purpose: "Converts markdown into slide HTML using markdown-it",
    exports: ["mdToHtml"],
    imports: ["pkg:markdown-it"],
    functions: [
      {
        id: "templates/mdToHtml.ts#mdToHtml",
        name: "mdToHtml",
        summary: "Transforms markdown to HTML and injects classes",
        sideEffects: ["render"],
      },
    ],
  },
  "content/sections.ts": {
    id: "content/sections.ts",
    path: "content/sections.ts",
    purpose: "Static section descriptors feeding the outline",
    exports: ["getSections"],
    imports: [],
    functions: [
      {
        id: "content/sections.ts#getSections",
        name: "getSections",
        summary: "Returns ordered sections with titles and markdown",
        sideEffects: [],
      },
    ],
  },
  "styles/print.css": {
    id: "styles/print.css",
    path: "styles/print.css",
    purpose: "Print/export layout for slides (A4/Letter, margins, overflow)",
    exports: [],
    imports: [],
    functions: [],
  },
  "pkg:markdown-it": {
    id: "pkg:markdown-it",
    path: "pkg:markdown-it",
    purpose: "External dependency for markdown rendering",
    exports: [],
    imports: [],
    functions: [],
  },
};

const MOCK_TREE: FolderNode = {
  id: "root",
  path: "/",
  purpose: "App + API + deck feature",
  children: [
    { id: "app", path: "app", purpose: "UI routes (Next.js)", children: [MOCK_FILES["app/page.tsx"]] },
    { id: "pages", path: "pages", purpose: "Next.js legacy pages + API routes", children: [MOCK_FILES["pages/api/compileDeck.ts"]] },
    { id: "deck", path: "deck", purpose: "Orchestrators and deck assembly", children: [MOCK_FILES["deck/compile.ts"]] },
    { id: "slides", path: "slides", purpose: "Slide builders", children: [MOCK_FILES["slides/buildOutline.ts"]] },
    { id: "templates", path: "templates", purpose: "Rendering templates", children: [MOCK_FILES["templates/mdToHtml.ts"]] },
    { id: "content", path: "content", purpose: "Static content", children: [MOCK_FILES["content/sections.ts"]] },
    { id: "styles", path: "styles", purpose: "Styling", children: [MOCK_FILES["styles/print.css"]] },
  ],
};

// Mock capabilities (end-to-end functions of the code)
const MOCK_CAPABILITIES: Capability[] = [
  {
    id: "cap:compile-deck",
    name: "Compile Slide Deck",
    purpose: "Generate an HTML slide deck from content sections and return it via API.",
    entryPoints: ["pages/api/compileDeck.ts"],
    orchestrators: ["deck/compile.ts#compile"],
    sources: ["content/sections.ts"],
    sinks: ["styles/print.css", "API response"],
    dataIn: ["request.query.variant", "sections markdown"],
    dataOut: ["htmlString: deck"],
    keyFiles: ["templates/mdToHtml.ts", "deck/compile.ts", "styles/print.css", "slides/buildOutline.ts"],
    steps: [
      { title: "Serve via API", description: "API route receives request and invokes compile()", fileId: "pages/api/compileDeck.ts" },
      { title: "Orchestrate", description: "compile() coordinates outline and rendering", fileId: "deck/compile.ts" },
      { title: "Build outline", description: "Read section descriptors and create slide structure", fileId: "slides/buildOutline.ts" },
      { title: "Render", description: "Convert markdown to HTML via template renderer", fileId: "templates/mdToHtml.ts" },
      { title: "Output", description: "Apply print styles and return HTML", fileId: "styles/print.css" },
    ],
  },
];

/** -----------------------------
 * Helper components & widgets
 * -----------------------------*/

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full border border-white/15 bg-white/5 px-2.5 py-0.5 text-xs text-white/80 backdrop-blur">
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

/** -----------------------------
 * Legend (badges & roles)
 * -----------------------------*/
function Legend() {
  return (
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
}

/** -----------------------------
 * Folder tree (collapsible)
 * -----------------------------*/

function TreeItem({ node, onSelect }: { node: FolderNode | FileNode; onSelect: (n: any) => void }) {
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
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="ml-5 border-l border-white/10 pl-3">
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
    <button onClick={() => onSelect(node)} className="group flex w-full items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-white/5">
      <FileIcon size={16} className="text-white/70" />
      <div>
        <div className="text-sm text-white/90">{node.path}</div>
        <div className="text-xs text-white/50">{node.purpose}</div>
      </div>
    </button>
  );
}

/** -----------------------------
 * Data Flow Bar (for capabilities)
 * -----------------------------*/
function DataFlowBar({ cap }: { cap: Capability | null }) {
  if (!cap) return null;
  return (
    <div className="mb-3 rounded-xl border border-white/10 bg-white/5 p-2 text-xs text-white/80">
      <div className="flex flex-wrap items-center gap-2">
        <Badge>Entry: {cap.entryPoints.map(f => f.split('/').pop()).join(', ')}</Badge>
        <Badge>Data in: {cap.dataIn.join(', ') || '—'}</Badge>
        <Badge>Data out: {cap.dataOut.join(', ') || '—'}</Badge>
        <Badge>Sources: {cap.sources.map(f => f.split('/').pop()).join(', ') || '—'}</Badge>
        <Badge>Sinks: {cap.sinks.map(s => (s.includes('/') ? s.split('/').pop() : s)).join(', ') || '—'}</Badge>
      </div>
    </div>
  );
}

/** -----------------------------
 * Simple Flow Graph (SVG)
 * -----------------------------*/

type GraphNode = { id: string; label: string; x: number; y: number };

type GraphEdge = { from: string; to: string };

function buildDemoGraph(focus: string | null) {
  const layout: GraphNode[] = [
    { id: "app/page.tsx", label: "page.tsx", x: 80, y: 170 },
    { id: "pages/api/compileDeck.ts", label: "compileDeck.ts", x: 250, y: 170 },
    { id: "deck/compile.ts", label: "compile.ts", x: 430, y: 170 },
    { id: "slides/buildOutline.ts", label: "buildOutline.ts", x: 620, y: 120 },
    { id: "templates/mdToHtml.ts", label: "mdToHtml.ts", x: 620, y: 220 },
    { id: "content/sections.ts", label: "sections.ts", x: 800, y: 120 },
    { id: "styles/print.css", label: "print.css", x: 800, y: 240 },
  ];
  const edges: GraphEdge[] = [
    { from: "app/page.tsx", to: "pages/api/compileDeck.ts" },
    { from: "pages/api/compileDeck.ts", to: "deck/compile.ts" },
    { from: "deck/compile.ts", to: "slides/buildOutline.ts" },
    { from: "deck/compile.ts", to: "templates/mdToHtml.ts" },
    { from: "slides/buildOutline.ts", to: "content/sections.ts" },
    { from: "deck/compile.ts", to: "styles/print.css" },
  ];
  return { nodes: layout, edges, focus };
}

function FlowGraph({ focus, highlighted = [], onSelect }: { focus: string | null; highlighted?: string[]; onSelect?: (id: string) => void }) {
  const graph = useMemo(() => buildDemoGraph(focus), [focus]);
  return (
    <div className="relative h-[360px] w-full rounded-2xl border border-white/10 bg-gradient-to-b from-white/5 to-white/0 p-3 backdrop-blur">
      <svg className="h-full w-full">
        {graph.edges.map((e, i) => {
          const a = graph.nodes.find((n) => n.id === e.from)!;
          const b = graph.nodes.find((n) => n.id === e.to)!;
          const edgeHot = [focus, ...highlighted].includes(e.from) || [focus, ...highlighted].includes(e.to);
          return (
            <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="currentColor" className={edgeHot ? "text-emerald-300" : "text-white/30"} strokeWidth={edgeHot ? 2 : 1.5} markerEnd="url(#arrow)" />
          );
        })}
        <defs>
          <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
            <path d="M0,0 L0,6 L6,3 z" fill="currentColor" className="text-white/30" />
          </marker>
        </defs>
        {graph.nodes.map((n) => {
          const isFocus = focus === n.id;
          const isHi = highlighted.includes(n.id);
          return (
            <g key={n.id} transform={`translate(${n.x - 36}, ${n.y - 18})`} onClick={() => onSelect?.(n.id)} style={{ cursor: 'pointer' }}>
              <rect width="120" height="32" rx="8" stroke="currentColor" strokeWidth={isFocus || isHi ? 2 : 1} className={`fill-white/10 ${isFocus || isHi ? 'text-emerald-300' : 'text-white/20'}`} />
              <text x="10" y="20" className="fill-white text-xs">{n.label}</text>
            </g>
          );
        })}
      </svg>
      <div className="absolute left-3 top-3 flex items-center gap-2 text-xs text-white/70">
        <GitBranch size={14} /> Focused feature flow
      </div>
    </div>
  );
}

/** -----------------------------
 * Details / Steps / Suggestions
 * -----------------------------*/

function FileCard({ file, selectedCap, novice }: { file: FileNode; selectedCap: Capability | null; novice: boolean }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-white/90">
      <div className="mb-1 flex items-center gap-2 text-sm font-medium">
        <FileIcon size={16} className="text-white/70" /> {file.path}
      </div>
      <p className="mb-2 text-xs text-white/70">{file.purpose}</p>
      <div className="flex flex-wrap items-center gap-2">
        {file.exports.length > 0 && <Badge>exports: {file.exports.join(", ")}</Badge>}
        {file.functions.length > 0 && <Badge>funcs: {file.functions.length}</Badge>}
        {file.imports.length > 0 && <Badge>imports: {file.imports.length}</Badge>}
        {/* role badges based on selected capability */}
        {selectedCap && selectedCap.entryPoints.includes(file.path) && <Badge>Entry point</Badge>}
        {selectedCap && selectedCap.orchestrators.some(o => o.split('#')[0] === file.path) && <Badge>Orchestrator</Badge>}
        {selectedCap && selectedCap.sources.includes(file.path) && <Badge>Source</Badge>}
        {selectedCap && selectedCap.sinks.includes(file.path) && <Badge>Sink</Badge>}
        {selectedCap && selectedCap.keyFiles.includes(file.path) && <Badge>Key file</Badge>}
      </div>
      {novice && (
        <div className="mt-2 rounded-xl bg-white/5 p-2 text-xs text-white/80">
          <span className="font-medium">In plain English:</span> {file.purpose}
        </div>
      )}
    </div>
  );
}

function StepsPanel({
  steps,
  onHover,
  onSelect,
}: {
  steps: { title: string; description: string; fileId?: string }[];
  onHover?: (fileId?: string) => void;
  onSelect?: (fileId?: string) => void;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-white/90">
      <SectionTitle icon={ListTree} title="Narrated steps" />
      <ol className="mt-2 space-y-2 text-sm">
        {steps.map((s, i) => (
          <li key={i} className="flex cursor-pointer items-start gap-2 rounded-lg p-1 hover:bg-white/5" onMouseEnter={() => onHover?.(s.fileId)} onMouseLeave={() => onHover?.(undefined)} onClick={() => onSelect?.(s.fileId)}>
            <span className="mt-0.5 inline-flex h-5 w-5 items-center justify-center rounded-full bg-white/10 text-xs text-white/80">{i + 1}</span>
            <div>
              <div className="font-medium">{s.title}</div>
              <div className="text-white/70">{s.description}</div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function CapabilityCard({ cap, onFocus, onSelect }: { cap: Capability; onFocus: () => void; onSelect: () => void }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-white/90">
      <div className="mb-1 text-sm font-semibold">{cap.name}</div>
      <div className="mb-2 text-xs text-white/70">{cap.purpose}</div>
      <div className="mb-2 flex flex-wrap gap-2 text-xs">
        <Badge>entry: {cap.entryPoints.length}</Badge>
        <Badge>orchestrators: {cap.orchestrators.length}</Badge>
        <Badge>sources: {cap.sources.length}</Badge>
        <Badge>sinks: {cap.sinks.length}</Badge>
      </div>
      <div className="text-xs text-white/60">Data in: {cap.dataIn.join(', ')}<br/>Data out: {cap.dataOut.join(', ')} </div>
      <div className="mt-3 flex gap-2">
        <button onClick={onFocus} className="rounded-md bg-white/10 px-2 py-1 text-xs hover:bg-white/15">Focus in graph</button>
        <button onClick={onSelect} className="rounded-md bg-white/10 px-2 py-1 text-xs hover:bg-white/15">Show steps</button>
      </div>
    </div>
  );
}

function Suggestions({ items, onSelect }: { items: { fileId: string; rationale: string; confidence: "High" | "Med" | "Low" }[]; onSelect?: (fileId: string) => void }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-white/90">
      <SectionTitle icon={Wand2} title="Edit suggestions" />
      <ul className="mt-2 space-y-2 text-sm">
        {items.map((it, i) => (
          <li key={i} className="flex cursor-pointer items-start justify-between gap-3 rounded-xl bg-white/5 p-2 hover:bg-white/10" onClick={() => onSelect?.(it.fileId)}>
            <div>
              <div className="font-medium">{it.fileId}</div>
              <div className="text-white/70">{it.rationale}</div>
            </div>
            <Chip>{it.confidence}</Chip>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** -----------------------------
 * Lightweight self-tests (debug aid)
 * -----------------------------*/

type TestResult = { name: string; pass: boolean; details?: string };

function runSelfTests(): TestResult[] {
  const results: TestResult[] = [];
  try {
    // T1: file ids match paths
    const t1 = Object.values(MOCK_FILES).every((f) => f.id === f.path);
    results.push({ name: "File ids match paths", pass: t1, details: t1 ? "ok" : "mismatch found" });

    // T2: imports exist (allow externals like pkg:*)
    const missingImports: string[] = [];
    Object.values(MOCK_FILES).forEach((f) => {
      f.imports.forEach((imp) => {
        if (!imp.startsWith("pkg:") && !MOCK_FILES[imp]) missingImports.push(`${f.path} -> ${imp}`);
      });
    });
    results.push({ name: "Imports resolve", pass: missingImports.length === 0, details: missingImports.join(", ") });

    // T3: capability steps reference existing files
    const badSteps = MOCK_CAPABILITIES.flatMap((c) => c.steps.map((s) => s.fileId!).filter((id) => !MOCK_FILES[id]));
    results.push({ name: "Capability steps point to files", pass: badSteps.length === 0, details: badSteps.join(", ") });

    // T4: graph nodes exist in mock files
    const nodes = buildDemoGraph(null).nodes.map((n) => n.id);
    const missingNodes = nodes.filter((n) => !MOCK_FILES[n]);
    results.push({ name: "Graph nodes exist", pass: missingNodes.length === 0, details: missingNodes.join(", ") });
  } catch (e: any) {
    results.push({ name: "Self-test runner crashed", pass: false, details: String(e?.message || e) });
  }
  return results;
}

function TestsPanel({ results }: { results: TestResult[] }) {
  const allPass = results.every((r) => r.pass);
  return (
    <div className="mt-6 rounded-2xl border border-white/10 bg-white/5 p-3 text-white/90">
      <SectionTitle icon={PanelsTopLeft} title="Self-tests" />
      <div className="mt-2 text-xs text-white/70">{allPass ? "All tests passed" : "Some tests failed (see below)"}</div>
      <ul className="mt-2 space-y-1 text-xs">
        {results.map((r, i) => (
          <li key={i} className="flex items-start gap-2">
            <span className={`mt-0.5 inline-flex h-4 w-4 items-center justify-center rounded ${r.pass ? 'bg-emerald-500/30' : 'bg-rose-500/30'}`}> {r.pass ? '✓' : '!'}</span>
            <div>
              <div className="font-medium">{r.name}</div>
              {r.details && <div className="text-white/60">{r.details}</div>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** -----------------------------
 * Upload Interface
 * -----------------------------*/
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

/** -----------------------------
 * Main component
 * -----------------------------*/

export default function ProvisUIDemo() {
  // Real data states
  const [repoId, setRepoId] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<CapabilitySummary[]>([]);
  const [currentCapability, setCurrentCapability] = useState<CapabilityDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [qaResponse, setQaResponse] = useState<string | null>(null);
  
  // UI states
  const [selectedFile, setSelectedFile] = useState<FileNode | null>(null);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"understand" | "fix" | "add" | "remove">("understand");
  const [fnView, setFnView] = useState<'code' | 'capabilities'>('capabilities');
  const [selectedCap, setSelectedCap] = useState<Capability | null>(null);
  const [manualFocus, setManualFocus] = useState<string | null>(null);
  const [novice, setNovice] = useState<boolean>(true);
  const [highlighted, setHighlighted] = useState<string[]>([]);
  const [scope, setScope] = useState<'all' | 'app' | 'pages' | 'deck' | 'slides' | 'templates' | 'content' | 'styles'>('all');
  const [testResults, setTestResults] = useState<TestResult[]>([]);

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
            
            // Convert to UI format
            const convertedCap: Capability = {
              id: detailResponse.data.id,
              name: detailResponse.data.name,
              purpose: detailResponse.data.purpose,
              entryPoints: detailResponse.data.entryPoints,
              orchestrators: detailResponse.data.orchestrators,
              sources: detailResponse.data.sources,
              sinks: detailResponse.data.sinks,
              dataIn: detailResponse.data.dataIn,
              dataOut: detailResponse.data.dataOut,
              keyFiles: detailResponse.data.keyFiles,
              steps: detailResponse.data.steps
            };
            setSelectedCap(convertedCap);
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

  // naive query mode routing (demo)
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
    setLoading(true);
    
    try {
      // Use the QA endpoint to ask questions about the repository
      const response = await apiClient.askQuestion(repoId, query);
      if (response.data) {
        console.log('QA Response:', response.data);
        setQaResponse(JSON.stringify(response.data, null, 2));
      } else if (response.error) {
        console.error('QA Error:', response.error);
        setQaResponse(`Error: ${response.error}`);
      }
    } catch (error) {
      console.error('Failed to process query:', error);
    } finally {
      setLoading(false);
    }
  };

  // demo: pick focus based on keywords or manual selection
  const focusFileId = useMemo(() => {
    if (manualFocus) return manualFocus;
    const q = query.toLowerCase();
    if (q.includes("outline")) return "slides/buildOutline.ts";
    if (q.includes("markdown") || q.includes("html")) return "templates/mdToHtml.ts";
    if (q.includes("print") || q.includes("css")) return "styles/print.css";
    if (q.includes("api")) return "pages/api/compileDeck.ts";
    return "deck/compile.ts";
  }, [query, manualFocus]);

  const steps = useMemo(() => {
    if (selectedCap) return selectedCap.steps;
    return [
      { title: "Orchestrate deck build", description: "deck/compile.ts coordinates outline and rendering, then writes output", fileId: "deck/compile.ts" },
      { title: "Build slide outline", description: "slides/buildOutline.ts reads content/sections.ts to form structure", fileId: "slides/buildOutline.ts" },
      { title: "Render markdown to HTML", description: "templates/mdToHtml.ts converts markdown using markdown-it", fileId: "templates/mdToHtml.ts" },
      { title: "Serve via API", description: "pages/api/compileDeck.ts invokes compile() and returns HTML", fileId: "pages/api/compileDeck.ts" },
    ];
  }, [selectedCap]);

  const scopedTree = useMemo(() => {
    if (scope === 'all') return MOCK_TREE;
    const child = (MOCK_TREE.children as any[]).find((n) => (n as any).path === scope);
    return { id: 'root', path: '/', purpose: MOCK_TREE.purpose, children: child ? [child] : [] } as FolderNode;
  }, [scope]);

  const suggestions = useMemo(() => {
    if (mode === "fix") {
      return [
        { fileId: "templates/mdToHtml.ts", rationale: "Handles image tags and layout; likely source of rendering glitches", confidence: "High" as const },
        { fileId: "styles/print.css", rationale: "Print margins/overflow may clip slides", confidence: "Med" as const },
        { fileId: "deck/compile.ts", rationale: "Orchestrates rendering; adjust pipeline or sanitization", confidence: "Med" as const },
      ];
    }
    if (mode === "add") {
      return [
        { fileId: "pages/api/compileDeck.ts", rationale: "Add endpoint parameter to support new deck variant", confidence: "High" as const },
        { fileId: "deck/compile.ts", rationale: "Insert branching to call new renderer", confidence: "High" as const },
        { fileId: "templates/mdToHtml.ts", rationale: "Implement renderer for new slide block type", confidence: "Med" as const },
      ];
    }
    if (mode === "remove") {
      return [
        { fileId: "slides/buildOutline.ts", rationale: "Removing an outline feature affects callers in compile.ts", confidence: "Med" as const },
        { fileId: "content/sections.ts", rationale: "Update section map to avoid dead references", confidence: "Med" as const },
      ];
    }
    return [
      { fileId: "deck/compile.ts", rationale: "Central orchestrator — start here to grasp the flow", confidence: "High" as const },
      { fileId: "slides/buildOutline.ts", rationale: "Explains the structure of slides", confidence: "High" as const },
    ];
  }, [mode]);

  // Run self-tests on mount and check for existing repo
  useEffect(() => {
    const results = runSelfTests();
    setTestResults(results);
    const summary = results.map((r) => `${r.pass ? 'PASS' : 'FAIL'}: ${r.name}${r.details ? ' — ' + r.details : ''}`).join('\n');
    // eslint-disable-next-line no-console
    console.log('[Provis self-tests]\n' + summary);
    
    // Try to load existing repository
    const existingRepoId = 'repo_6e5a3029'; // The repository we know exists
    setRepoId(existingRepoId);
    loadRepositoryData(existingRepoId);
  }, []);

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
    <div className="min-h-[720px] w-full bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 p-6 text-white">
      {/* Header */}
      <div className="mx-auto max-w-6xl">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl bg-white/10 px-3 py-1.5 font-semibold tracking-wide backdrop-blur">Provis</div>
            <div className="hidden text-sm text-white/60 md:block">Drop a repo. Understand. Fix. Add. Remove.</div>
          </div>
          <div className="text-xs text-white/50">
            {currentCapability ? 
              `Repository ${repoId} • ${Object.keys(currentCapability.nodeIndex || {}).length} files • ${capabilities.length} capabilities` :
              `Repository ${repoId} • Loading...`
            }
          </div>
        </div>

        {/* Query bar */}
        <div className="mb-6 flex items-center gap-2">
          <div className="flex flex-1 items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 backdrop-blur">
            <Search size={16} className="text-white/60" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && runQuery()} placeholder="Ask anything: how does the deck render? fix images cut off? add speaker notes?" className="w-full bg-transparent text-sm text-white placeholder:text-white/50 focus:outline-none" />
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
            <button onClick={() => setNovice(v => !v)} className={`rounded-xl px-3 py-1.5 text-sm ${novice ? 'bg-emerald-400/20 text-emerald-200' : 'bg-white/10 text-white'} hover:bg-white/15`} title="Show plain-English explanations and data flow">{novice ? 'Novice mode: ON' : 'Novice mode: OFF'}</button>
          </div>
          <div className="hidden items-center gap-2 md:flex">
            <div className="inline-flex items-center gap-1"><PanelsTopLeft size={14} className="mr-1" /> <span className="text-xs">{mode}</span></div>
          </div>
        </div>
        {/* Starter & mode chips */}
        <div className="-mt-4 mb-4 flex flex-wrap gap-2 text-xs text-white/70">
          {['understand','fix','add','remove'].map(m => (
            <button key={m} onClick={() => setMode(m as any)} className={`rounded-md px-2 py-0.5 ${mode===m ? 'bg-white/15' : 'bg-white/5'} hover:bg-white/10`}>{m}</button>
          ))}
          <span className="mx-2 opacity-50">•</span>
          {[
            {q: 'how does the deck render?', f: 'deck/compile.ts'},
            {q: 'fix images cut off', f: 'styles/print.css'},
            {q: 'where does data come from?', f: 'content/sections.ts'},
            {q: 'add speaker notes', f: 'templates/mdToHtml.ts'},
          ].map((s) => (
            <button key={s.q} onClick={() => { setQuery(s.q); setManualFocus(s.f); }} className="rounded-md bg-white/5 px-2 py-0.5 hover:bg-white/10">{s.q}</button>
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
                    <button key={s} onClick={() => setScope(s as any)} className={`rounded-md px-2 py-0.5 ${scope===s ? 'bg-white/15' : 'bg-white/5'} hover:bg-white/10`}>{s}</button>
                  ))}
                </div>
                {currentCapability ? (
                  <div className="space-y-2">
                    {Object.entries(currentCapability.nodeIndex).map(([path, node]) => (
                      <button 
                        key={path}
                        onClick={() => {
                          const mockFile: FileNode = {
                            id: path,
                            path: path,
                            purpose: `${node.role} component in ${node.lane} layer`,
                            exports: [],
                            imports: node.incoming || [],
                            functions: []
                          };
                          setSelectedFile(mockFile);
                          setManualFocus(path);
                        }}
                        className="group flex w-full items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-white/5 text-left"
                      >
                        <FileIcon size={16} className="text-white/70" />
                        <div>
                          <div className="text-sm text-white/90">{path.split('/').pop()}</div>
                          <div className="text-xs text-white/50">{node.role} • {node.lane}</div>
                        </div>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="text-center text-white/50 py-8">Loading repository structure...</div>
                )}
              </div>
            </div>
          </div>

          {/* Center: Flow graph */}
          <div className="md:col-span-4">
            <SectionTitle icon={GitBranch} title="Focused flow" />
            <div className="mt-3">
              <DataFlowBar cap={selectedCap} />
              {currentCapability ? (
                <div className="relative h-[360px] w-full rounded-2xl border border-white/10 bg-gradient-to-b from-white/5 to-white/0 p-3 backdrop-blur">
                  <div className="text-center text-white/70 flex items-center justify-center h-full">
                    <div>
                      <GitBranch size={24} className="mx-auto mb-2 opacity-50" />
                      <div className="text-sm">Flow visualization coming soon</div>
                      <div className="text-xs text-white/50 mt-1">
                        {Object.keys(currentCapability.nodeIndex).length} nodes • {capabilities.length} capabilities
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="h-[360px] w-full rounded-2xl border border-white/10 bg-white/5 flex items-center justify-center">
                  <RefreshCw className="w-6 h-6 animate-spin text-white/50" />
                </div>
              )}
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
              {selectedFile ? <FileCard file={selectedFile} selectedCap={selectedCap} novice={novice} /> : (
                <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-center text-white/70">Select a file from the folder map to see details.</div>
              )}
              <StepsPanel steps={steps} onHover={(fid) => setHighlighted(fid ? [fid] : [])} onSelect={(fid) => { if (!fid) return; const f = (MOCK_FILES as any)[fid]; if (f) setSelectedFile(f); setManualFocus(fid); }} />
              <Suggestions items={suggestions} onSelect={(fid) => { const f = (MOCK_FILES as any)[fid]; if (f) setSelectedFile(f); setManualFocus(fid); }} />
            </div>
          </div>
        </div>

        {/* Functions & Capabilities */}
        <div className="mt-6 rounded-2xl border border-white/10 bg-white/5 p-4">
          <SectionTitle icon={ListTree} title="Functions & Capabilities" />
          <div className="mt-3">
            {/* Toggle */}
            <div className="mb-3 inline-flex overflow-hidden rounded-xl border border-white/10 text-xs">
              <button onClick={() => setFnView('capabilities')} className={`px-3 py-1.5 ${fnView==='capabilities' ? 'bg-white/15' : 'bg-white/5'}`}>Capabilities</button>
              <button onClick={() => setFnView('code')} className={`px-3 py-1.5 ${fnView==='code' ? 'bg-white/15' : 'bg-white/5'}`}>Code functions</button>
            </div>

            {fnView === 'capabilities' ? (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
                {capabilities.map((cap) => {
                  const uiCap: Capability = {
                    id: cap.id,
                    name: cap.name,
                    purpose: cap.purpose,
                    entryPoints: cap.entryPoints,
                    orchestrators: [],
                    sources: cap.sources,
                    sinks: cap.sinks,
                    dataIn: cap.dataIn,
                    dataOut: cap.dataOut,
                    keyFiles: cap.keyFiles,
                    steps: []
                  };
                  return (
                    <CapabilityCard 
                      key={cap.id} 
                      cap={uiCap} 
                      onFocus={() => setManualFocus(cap.keyFiles[0])} 
                      onSelect={async () => {
                        if (repoId) {
                          const detailResponse = await apiClient.getCapability(repoId, cap.id);
                          if (detailResponse.data) {
                            const convertedCap: Capability = {
                              id: detailResponse.data.id,
                              name: detailResponse.data.name,
                              purpose: detailResponse.data.purpose,
                              entryPoints: detailResponse.data.entryPoints,
                              orchestrators: detailResponse.data.orchestrators,
                              sources: detailResponse.data.sources,
                              sinks: detailResponse.data.sinks,
                              dataIn: detailResponse.data.dataIn,
                              dataOut: detailResponse.data.dataOut,
                              keyFiles: detailResponse.data.keyFiles,
                              steps: detailResponse.data.steps
                            };
                            setSelectedCap(convertedCap);
                          }
                        }
                      }} 
                    />
                  );
                })}
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
                {Object.values(MOCK_FILES).flatMap((f) => f.functions.map((fn) => ({ fn, file: f }))).map(({ fn, file }) => (
                  <div key={fn.id} className="rounded-xl border border-white/10 bg-white/5 p-3">
                    <div className="mb-1 text-sm font-medium">{fn.name} <span className="text-white/50">in</span> {file.path}</div>
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

        {/* QA Response */}
        {qaResponse && (
          <div className="mt-6 rounded-2xl border border-white/10 bg-white/5 p-3 text-white/90">
            <SectionTitle icon={Search} title="Query Response" />
            <div className="mt-2 text-xs text-white/70">
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

        {/* Self-tests */}
        <TestsPanel results={testResults} />
      </div>
    </div>
  );
}
