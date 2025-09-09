import { Suspense } from 'react';
import Link from 'next/link';
import { fetchCapabilities } from '@/lib/api';
import { GitBranch } from 'lucide-react';

async function CapabilitiesList({ repoId }: { repoId: string }) {
  const { index } = await fetchCapabilities(repoId);
  
  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-2xl font-semibold mb-6">Capabilities</h1>
      
      <div className="grid gap-4">
        {index.map(cap => (
          <Link 
            key={cap.id}
            href={`/repo/${repoId}/capabilities/${cap.id}`}
            className="block p-4 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10"
          >
            <div className="flex items-center gap-2">
              <GitBranch className="w-4 h-4 text-white/70" />
              <span className="font-medium">{cap.name}</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

export default function CapabilitiesPage({
  params: { repoId }
}: {
  params: { repoId: string; }
}) {
  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-950 to-slate-900 text-slate-100">
      <Suspense fallback={
        <div className="flex items-center justify-center min-h-screen">
          Loading capabilities...
        </div>
      }>
        <CapabilitiesList repoId={repoId} />
      </Suspense>
    </div>
  );
}
