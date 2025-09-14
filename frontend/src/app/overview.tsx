import React, { useState } from "react";
import { Folder, File, GitBranch, Globe, Package, ListTree, ChevronRight } from "lucide-react";

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full border border-white/15 bg-white/5 px-2 py-0.5 text-[10px] text-white/80">
      {children}
    </span>
  );
}

// ---------- Mock repo structure ----------
export type FileNode = { id: string; label: string; purpose: string; lines: number };
export type FolderNode = { id: string; label: string; purpose: string; children?: (FolderNode | FileNode)[] };

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
};

const REPO: FolderNode = {
  id: "root",
  label: "/",
  purpose: "Root of repository",
  children: [
    {
      id: "app",
      label: "app",
      purpose: "UI routes (Next.js)",
      children: [
        { id: "app/page.tsx", label: "page.tsx", purpose: "Landing page UI", lines: 120 },
        { id: "app/dashboard.tsx", label: "dashboard.tsx", purpose: "Main dashboard UI", lines: 220 },
      ],
    },
    {
      id: "pages",
      label: "pages",
      purpose: "API routes",
      children: [
        { id: "pages/api/appointments.ts", label: "appointments.ts", purpose: "CRUD endpoints", lines: 300 },
        { id: "pages/api/payments.ts", label: "payments.ts", purpose: "Stripe webhooks", lines: 180 },
      ],
    },
    {
      id: "core",
      label: "core",
      purpose: "Business logic",
      children: [
        { id: "core/scheduling.ts", label: "scheduling.ts", purpose: "Availability engine", lines: 400 },
        { id: "core/billing.ts", label: "billing.ts", purpose: "Payment orchestration", lines: 500 },
      ],
    },
    { id: "db", label: "db", purpose: "Database schema", children: [{ id: "db/schema.prisma", label: "schema.prisma", purpose: "ORM schema", lines: 220 }] },
    { id: "lib", label: "lib", purpose: "Utility functions", children: [{ id: "lib/helpers.ts", label: "helpers.ts", purpose: "General helpers", lines: 150 }] },
  ],
};

const CAPABILITIES: Capability[] = [
  {
    id: "cap1",
    name: "Schedule Appointment",
    desc: "Handle booking requests and save to DB.",
    entryPoints: ["pages/api/appointments.ts"],
    keyFiles: ["core/scheduling.ts", "db/schema.prisma"],
    dataIn: ["appointment_request", "user_preferences"],
    dataOut: ["appointment_confirmation", "calendar_event"],
    steps: [
      { title: "Receive Booking Request", description: "API endpoint receives appointment booking request with time slots and user details", fileId: "pages/api/appointments.ts" },
      { title: "Validate Time Slot", description: "Check availability against existing appointments and business hours", fileId: "core/scheduling.ts" },
      { title: "Check Staff Availability", description: "Verify that requested staff member is available for the time slot", fileId: "core/scheduling.ts" },
      { title: "Reserve Time Slot", description: "Create temporary reservation to prevent double-booking", fileId: "db/schema.prisma" },
      { title: "Save to Database", description: "Persist the confirmed appointment to the database", fileId: "db/schema.prisma" },
      { title: "Send Confirmation", description: "Trigger confirmation email/SMS to customer and staff", fileId: "pages/api/appointments.ts" },
    ],
  },
  {
    id: "cap2",
    name: "Process Payment",
    desc: "Orchestrate Stripe payments and update invoices.",
    entryPoints: ["pages/api/payments.ts"],
    keyFiles: ["core/billing.ts", "db/schema.prisma"],
    dataIn: ["payment_intent", "customer_data"],
    dataOut: ["payment_result", "invoice_update"],
    steps: [
      { title: "Initialize Payment", description: "Create Stripe payment intent with amount and customer details", fileId: "pages/api/payments.ts" },
      { title: "Validate Payment Data", description: "Verify payment amount, currency, and customer information", fileId: "core/billing.ts" },
      { title: "Process with Stripe", description: "Submit payment to Stripe and handle the response", fileId: "core/billing.ts" },
      { title: "Update Invoice Status", description: "Mark invoice as paid and update payment records", fileId: "db/schema.prisma" },
      { title: "Send Receipt", description: "Email payment receipt to customer", fileId: "pages/api/payments.ts" },
      { title: "Trigger Webhooks", description: "Notify other systems of successful payment", fileId: "pages/api/payments.ts" },
    ],
  },
  {
    id: "cap3",
    name: "Send Reminder",
    desc: "Trigger SMS/Email reminders via Twilio/SendGrid.",
    entryPoints: ["core/scheduling.ts"],
    keyFiles: ["lib/helpers.ts"],
    dataIn: ["appointment_data", "reminder_template"],
    dataOut: ["notification_sent", "delivery_status"],
    steps: [
      { title: "Check Upcoming Appointments", description: "Query database for appointments needing reminders", fileId: "core/scheduling.ts" },
      { title: "Generate Reminder Content", description: "Create personalized reminder message with appointment details", fileId: "lib/helpers.ts" },
      { title: "Choose Delivery Method", description: "Determine whether to send SMS, email, or both based on preferences", fileId: "lib/helpers.ts" },
      { title: "Send via Twilio/SendGrid", description: "Deliver reminder through appropriate service", fileId: "lib/helpers.ts" },
      { title: "Track Delivery Status", description: "Log reminder sent and track delivery confirmation", fileId: "core/scheduling.ts" },
    ],
  },
  {
    id: "cap4",
    name: "Manage Staff",
    desc: "CRUD for staff members and permissions.",
    entryPoints: ["pages/api/staff.ts"],
    keyFiles: ["db/schema.prisma"],
    dataIn: ["staff_data", "permission_levels"],
    dataOut: ["staff_record", "access_granted"],
    steps: [
      { title: "Receive Staff Request", description: "API endpoint receives request to create, update, or delete staff", fileId: "pages/api/staff.ts" },
      { title: "Validate Permissions", description: "Check if requesting user has admin rights to manage staff", fileId: "pages/api/staff.ts" },
      { title: "Process Staff Data", description: "Validate staff information, schedules, and role assignments", fileId: "db/schema.prisma" },
      { title: "Update Database", description: "Create or modify staff record in the database", fileId: "db/schema.prisma" },
      { title: "Configure Access", description: "Set up authentication and authorization for the staff member", fileId: "pages/api/staff.ts" },
    ],
  },
];

// ---------- Recursive folder/file viewer ----------
function FolderTree({ node, onSelect }: { node: FolderNode | FileNode; onSelect: (n: FolderNode | FileNode) => void }) {
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
      <div className="mt-1 text-[10px] text-white/50">~{file.lines} LOC</div>
    </div>
  );
}

// ---------- Capability Steps Panel ----------
function CapabilitySteps({ capability, onFileSelect }: { capability: Capability | null; onFileSelect: (fileId: string) => void }) {
  if (!capability) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-center text-white/60">
        <ListTree size={24} className="mx-auto mb-2 opacity-50" />
        <p className="text-sm">Select a capability to see its step-by-step process</p>
      </div>
    );
  }

  return (
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
  );
}

// ---------- Main Overview ----------
export default function RepoOverviewMockup() {
  const [focus, setFocus] = useState<FolderNode | FileNode>(REPO);
  const [selectedCapability, setSelectedCapability] = useState<Capability | null>(null);

  const isFolder = (n: any): n is FolderNode => (n as FolderNode).children !== undefined;

  const handleFileSelect = (fileId: string) => {
    // Find the file in the repo structure
    const findFile = (node: FolderNode | FileNode): FileNode | null => {
      if (!isFolder(node)) {
        return node.id === fileId ? node : null;
      }
      for (const child of node.children || []) {
        const result = findFile(child);
        if (result) return result;
      }
      return null;
    };
    
    const file = findFile(REPO);
    if (file) {
      setFocus(file);
    }
  };

  return (
    <div className="min-h-screen w-full bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 p-6 text-white">
      <div className="mx-auto max-w-7xl space-y-6">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-white mb-2">Repository Overview</h1>
          <p className="text-white/60">Explore your codebase structure, capabilities, and dependencies</p>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* Left column - Repository structure */}
          <div className="lg:col-span-4 space-y-6">
            {/* Repo structure */}
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white/90">
                <Folder size={16}/> Repository Structure
              </h2>
              <FolderTree node={REPO} onSelect={setFocus} />
            </div>

            {/* Integrations and dependencies */}
            <div className="space-y-4">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white/90">
                  <Globe size={16}/> External Integrations
                </h2>
                <div className="flex flex-wrap gap-2 text-xs">
                  <Badge>Stripe</Badge>
                  <Badge>SendGrid</Badge>
                  <Badge>Twilio</Badge>
                  <Badge>Google Calendar</Badge>
                </div>
              </div>

              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white/90">
                  <Package size={16}/> Dependencies
                </h2>
                <div className="flex flex-wrap gap-2 text-xs">
                  <Badge>next</Badge>
                  <Badge>react</Badge>
                  <Badge>prisma</Badge>
                  <Badge>next-auth</Badge>
                  <Badge>zod</Badge>
                </div>
              </div>
            </div>
          </div>

          {/* Middle column - Focused node */}
          <div className="lg:col-span-4">
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <div className="text-sm font-semibold text-white/90">Focus: {"label" in focus ? focus.label : ""}</div>
              <div className="mt-1 text-xs text-white/70">{"purpose" in focus ? focus.purpose : ""}</div>
              {isFolder(focus) ? (
                <div className="mt-4 grid grid-cols-1 gap-2">
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
                      return <FileBlock key={c.id} file={c} />;
                    }
                  })}
                </div>
              ) : (
                "lines" in focus && <div className="mt-4"><FileBlock file={focus} /></div>
              )}
            </div>
          </div>

          {/* Right column - Steps panel */}
          <div className="lg:col-span-4">
            <CapabilitySteps capability={selectedCapability} onFileSelect={handleFileSelect} />
          </div>
        </div>

        {/* Repo capabilities */}
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white/90">
            <GitBranch size={16}/> Capabilities
          </h2>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
            {CAPABILITIES.map((cap) => (
              <div
                key={cap.id}
                className={`cursor-pointer rounded-lg border p-3 transition-all ${
                  selectedCapability?.id === cap.id
                    ? 'border-emerald-500/50 bg-emerald-500/10 shadow-lg shadow-emerald-500/10'
                    : 'border-white/10 bg-white/5 hover:border-white/20 hover:bg-white/10'
                }`}
                onClick={() => setSelectedCapability(cap)}
              >
                <div className="flex items-center gap-2">
                  <div className="font-medium text-white/90 text-sm">{cap.name}</div>
                  {selectedCapability?.id === cap.id && (
                    <div className="w-2 h-2 bg-emerald-400 rounded-full"></div>
                  )}
                </div>
                <div className="mt-1 text-xs text-white/70">{cap.desc}</div>
                <div className="mt-2 flex flex-wrap gap-1">
                  <Badge>steps: {cap.steps.length}</Badge>
                  <Badge>files: {cap.keyFiles.length}</Badge>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
