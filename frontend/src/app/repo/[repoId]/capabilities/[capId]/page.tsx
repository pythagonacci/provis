import { Suspense } from 'react';
import { fetchCapability } from '@/lib/api';
import { CapabilityView } from '@/components/capability/CapabilityView';

async function CapabilityContent({ 
  repoId, 
  capId 
}: { 
  repoId: string; 
  capId: string;
}) {
  const capability = await fetchCapability(repoId, capId);
  return <CapabilityView capability={capability} />;
}

export default function CapabilityPage({
  params: { repoId, capId }
}: {
  params: { repoId: string; capId: string; }
}) {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-gradient-to-b from-slate-950 to-slate-900 text-slate-100 flex items-center justify-center">
        Loading capability...
      </div>
    }>
      <CapabilityContent repoId={repoId} capId={capId} />
    </Suspense>
  );
}
