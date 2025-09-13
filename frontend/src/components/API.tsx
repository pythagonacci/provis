'use client';

import { Server } from 'lucide-react';
import { Title } from './shared/Title';
import { Chip } from './shared/Chip';

interface Endpoint {
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
}

interface APIProps {
  eps: Endpoint[];
  onSelect?: (id: string) => void;
}


export default function API({ eps, onSelect }: APIProps) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-white/90">
      <Title icon={Server} title="API" />
      <div className="mt-2 overflow-x-auto text-xs">
        <table className="w-full border-separate border-spacing-y-1">
          <thead className="text-white/60">
            <tr>
              <th className="text-left">Method</th>
              <th className="text-left">Path</th>
              <th className="text-left">Handler</th>
              <th className="text-left">Request</th>
              <th className="text-left">Response</th>
            </tr>
          </thead>
          <tbody>
            {eps.map(e => (
              <tr key={e.id}>
                <td className="py-1">
                  <Chip>{e.method}</Chip>
                </td>
                <td className="py-1">{e.path}</td>
                <td className="py-1">
                  <button 
                    className="underline decoration-white/20 underline-offset-4 hover:text-white" 
                    onClick={() => onSelect?.(e.handlerFile)}
                  >
                    {e.handlerFile}
                  </button>
                </td>
                <td className="py-1 text-white/70">
                  {e.request?.params && <div>params: {e.request.params.join(', ')}</div>}
                  {e.request?.query && <div>query: {e.request.query.join(', ')}</div>}
                  {e.request?.body && <div>body: {e.request.body}</div>}
                </td>
                <td className="py-1 text-white/70">{e.response?.type || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
