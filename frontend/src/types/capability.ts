export type Func = {
  id: string;
  name: string;
  summary: string;
  sideEffects: ("io" | "net" | "db" | "dom" | "render")[];
  callers?: string[]; // function ids
  callees?: string[]; // function ids
};

export type FileNode = {
  id: string;
  path: string;
  purpose: string;
  exports: string[];
  imports: string[]; // file ids
  functions: Func[];
};

export type FolderNode = {
  id: string;
  path: string;
  purpose: string;
  children: (FolderNode | FileNode)[];
};

// High-level capability = end-to-end functionality (e.g., "Compile slide deck")
export type Capability = {
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

export type GraphNode = { 
  id: string; 
  label: string; 
  x: number; 
  y: number; 
};

export type GraphEdge = { 
  from: string; 
  to: string; 
};

export type TestResult = { 
  name: string; 
  pass: boolean; 
  details?: string; 
};

export type Suggestion = {
  fileId: string;
  rationale: string;
  confidence: "High" | "Med" | "Low";
};

export type QueryMode = "understand" | "fix" | "add" | "remove";
export type Scope = 'all' | 'app' | 'pages' | 'deck' | 'slides' | 'templates' | 'content' | 'styles';
export type FunctionView = 'code' | 'capabilities';
