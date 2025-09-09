export type Entrypoint = {
  path: string;
  framework: string;
  kind: 'ui' | 'api' | 'webhook';
};

export type ControlFlowEdge = {
  from: string;
  to: string;
  kind: 'component' | 'http' | 'import' | 'call' | 'webhook' | 'queue' | 'worker';
};

export type DataItem = {
  type: string;
  name?: string;
  path?: string;
  key?: string;
  fields?: string[];
  client?: string;
  touches?: Touch[];
  example?: any;
};

export type Touch = {
  actorPath: string;
  action: 'read' | 'write' | 'enqueue' | 'consume' | 'call';
  via: 'repo' | 'http' | 'queue' | 'sdk';
  reason: string;
};

export type Policy = {
  type: 'middleware' | 'schemaGuard' | 'cors' | 'unknown';
  name: string;
  path: string;
  appliedAt?: string;
};

export type Contract = {
  name: string;
  kind: string;
  path: string;
  fields?: string[];
};

export type NarrativeStep = {
  label: string;
  detail?: string;
  scenario?: 'happy' | 'edge' | 'error';
};

export type Capability = {
  id: string;
  title: string;
  status: 'healthy' | 'degraded' | 'error';
  entrypoints: Entrypoint[];
  control_flow: ControlFlowEdge[];
  swimlanes: {
    web: string[];
    api: string[];
    workers: string[];
  };
  data_flow: {
    inputs: DataItem[];
    stores: DataItem[];
    externals: DataItem[];
  };
  policies: Policy[];
  contracts: Contract[];
  summaries: {
    file: Record<string, string>;
    folder: Record<string, string>;
    narrative: NarrativeStep[];
  };
};
