"use client";

import React, { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import type { Prospect, Deck, EmailBatch, EmailItem } from "../types";

type DeckState = {
  status: "idle" | "loading" | "ready";
  deck?: Deck;
  error?: string;
};

type EmailState = {
  status: "idle" | "loading" | "ready";
  batch?: EmailBatch;
  selectedId?: number;
  error?: string;
};

export default function Page() {
  const [prospects, setProspects] = useState<Prospect[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [deckByProspect, setDeckByProspect] = useState<Record<number, DeckState>>({});
  const [emailsByProspect, setEmailsByProspect] = useState<Record<number, EmailState>>({});
  const [showModal, setShowModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingProspect, setEditingProspect] = useState<Prospect | null>(null);
  const [rightPanelContent, setRightPanelContent] = useState<"deck" | "email" | null>(null);
  const [selectedDeck, setSelectedDeck] = useState<Deck | null>(null);
  const [selectedEmail, setSelectedEmail] = useState<EmailItem | null>(null);
  const [sentEmails, setSentEmails] = useState<Set<number>>(new Set());
  const [showPdfViewer, setShowPdfViewer] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfViewMode, setPdfViewMode] = useState<"modal" | "split">("modal");
  const [currentPdfDeckId, setCurrentPdfDeckId] = useState<number | null>(null);

  const [form, setForm] = useState<Partial<Prospect>>({
    company_name: "",
    contact_name: "",
    email: "",
    phone_number: "",
    industry: "",
    revenue_range: "",
    location: "",
    sale_motivation: "",
    signals: "",
    notes: "",
  });

  useEffect(() => {
    (async () => {
      try {
        const list = await api.listProspects();
        setProspects(list);
      } finally {
        setLoadingList(false);
      }
    })();
  }, []);

  const selectedEmailFromState: EmailItem | undefined = useMemo(() => {
    // find the currently selected email among any prospect
    for (const p of prospects) {
      const es = emailsByProspect[p.id];
      if (es?.status === "ready" && es.selectedId) {
        return es.batch!.items.find((i) => i.id === es.selectedId);
      }
    }
    return undefined;
  }, [emailsByProspect, prospects]);

  async function handleCreateProspect() {
    if (!form.company_name?.trim()) return;
    const created = await api.createProspect({
      company_name: form.company_name!.trim(),
      contact_name: form.contact_name?.trim() || undefined,
      email: form.email?.trim() || undefined,
      phone_number: form.phone_number?.trim() || undefined,
      industry: form.industry?.trim() || undefined,
      revenue_range: form.revenue_range?.trim() || undefined,
      location: form.location?.trim() || undefined,
      sale_motivation: form.sale_motivation?.trim() || undefined,
      signals: form.signals?.trim() || undefined,
      notes: form.notes?.trim() || undefined,
    });
    setProspects((p) => [created, ...p]);
    setShowModal(false);
    setForm({ company_name: "" });
  }

  function handleEditProspect(prospect: Prospect) {
    setEditingProspect(prospect);
    setForm({
      company_name: prospect.company_name,
      contact_name: prospect.contact_name || "",
      email: prospect.email || "",
      phone_number: prospect.phone_number || "",
      industry: prospect.industry || "",
      revenue_range: prospect.revenue_range || "",
      location: prospect.location || "",
      sale_motivation: prospect.sale_motivation || "",
      signals: prospect.signals || "",
      notes: prospect.notes || "",
    });
    setShowEditModal(true);
  }

  async function handleUpdateProspect() {
    if (!editingProspect || !form.company_name?.trim()) return;
    const updated = await api.updateProspect(editingProspect.id, {
      company_name: form.company_name!.trim(),
      contact_name: form.contact_name?.trim() || undefined,
      email: form.email?.trim() || undefined,
      phone_number: form.phone_number?.trim() || undefined,
      industry: form.industry?.trim() || undefined,
      revenue_range: form.revenue_range?.trim() || undefined,
      location: form.location?.trim() || undefined,
      sale_motivation: form.sale_motivation?.trim() || undefined,
      signals: form.signals?.trim() || undefined,
      notes: form.notes?.trim() || undefined,
    });
    setProspects((p) => p.map(prospect => prospect.id === updated.id ? updated : prospect));
    setShowEditModal(false);
    setEditingProspect(null);
    setForm({ company_name: "" });
  }

  async function handleGenerateDeck(p: Prospect) {
    setDeckByProspect((m) => ({ ...m, [p.id]: { status: "loading" } }));
    try {
      const deck = await api.generateDeck(p.id);
      setDeckByProspect((m) => ({ ...m, [p.id]: { status: "ready", deck } }));
    } catch (e: any) {
      setDeckByProspect((m) => ({ ...m, [p.id]: { status: "idle", error: e?.message || "Failed" } }));
      alert(`Deck generation failed: ${e?.message || ""}`);
    }
  }

  async function handleRenderAndDownload(p: Prospect) {
    const state = deckByProspect[p.id];
    const deckId = state?.deck?.id;
    if (!deckId) return;
    
    try {
      const rendered = await api.renderDeck(deckId);
      if (rendered.pdf_url) {
        // Add cache-busting parameter to ensure fresh PDF
        const cacheBustedUrl = `${rendered.pdf_url}?t=${Date.now()}`;
        setPdfUrl(cacheBustedUrl);
        setCurrentPdfDeckId(deckId);
        setShowPdfViewer(true);
        setDeckByProspect((m) => ({ ...m, [p.id]: { status: "ready", deck: rendered } }));
      }
    } catch (e: any) {
      alert(`PDF generation failed: ${e?.message || "Unknown error"}`);
    }
  }

  async function handleRefreshPdf() {
    if (!currentPdfDeckId) return;
    
    try {
      const rendered = await api.renderDeck(currentPdfDeckId);
      if (rendered.pdf_url) {
        // Add cache-busting parameter to ensure fresh PDF
        const cacheBustedUrl = `${rendered.pdf_url}?t=${Date.now()}`;
        setPdfUrl(cacheBustedUrl);
        // Update the deck in state
        setDeckByProspect((m) => {
          const owner = Object.keys(m).find((pid) =>
            m[+pid]?.deck?.id === currentPdfDeckId
          );
          if (!owner) return m;
          return { ...m, [+owner]: { ...m[+owner], deck: rendered } };
        });
        // Update the selected deck if it's the same one
        if (selectedDeck?.id === currentPdfDeckId) {
          setSelectedDeck(rendered);
        }
      }
    } catch (e: any) {
      alert(`PDF refresh failed: ${e?.message || "Unknown error"}`);
    }
  }

  function handleOpenDeck(deck: Deck) {
    setSelectedDeck(deck);
    setSelectedEmail(null);
    setRightPanelContent("deck");
  }

  function handleOpenEmail(email: EmailItem) {
    setSelectedEmail(email);
    setSelectedDeck(null);
    setRightPanelContent("email");
  }

  function toggleEmailSent(emailId: number) {
    setSentEmails(prev => {
      const newSet = new Set(prev);
      if (newSet.has(emailId)) {
        newSet.delete(emailId);
      } else {
        newSet.add(emailId);
      }
      return newSet;
    });
  }

  async function handleGenerateEmails(p: Prospect) {
    setEmailsByProspect((m) => ({ ...m, [p.id]: { status: "loading" } }));
    try {
      const batch = await api.generateEmails(p.id);
      setEmailsByProspect((m) => ({ ...m, [p.id]: { status: "ready", batch } }));
    } catch (e: any) {
      setEmailsByProspect((m) => ({ ...m, [p.id]: { status: "idle", error: e?.message || "Failed" } }));
      alert(`Email generation failed: ${e?.message || ""}`);
    }
  }

  function selectEmail(pId: number, emailId: number) {
    setEmailsByProspect((m) => ({ ...m, [pId]: { ...(m[pId] || { status: "ready" }), ...m[pId], selectedId: emailId } }));
  }

  return (
    <main className="min-h-screen bg-[#fcfbfa]">
      {/* Header */}
      <div className="sticky top-0 z-10 border-b border-gray-200 bg-white shadow-sm">
        <div className="mx-auto max-w-7xl px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <img src="/offdeal_logo.png" alt="OffDeal" className="h-16 w-auto" />
          </div>
          <div className="h-8 w-8 rounded-full bg-gray-300 grid place-items-center font-semibold text-sm text-gray-700">
            OE
          </div>
        </div>
      </div>

      {/* Body: table + right pane */}
      <div className="mx-auto max-w-7xl px-6 pb-6 grid grid-cols-12 gap-6 mt-8">
        <div className="col-span-8">
          <div className="mb-4">
            <button
              onClick={() => setShowModal(true)}
              className="rounded-lg bg-[#ebe5df] px-4 py-2 text-sm font-medium text-gray-700 hover:bg-[#e0d9d2] transition-colors border border-gray-300"
            >
              + Prospect
            </button>
          </div>
          <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
            <div className="grid grid-cols-5 bg-[#ebe5df] text-xs font-semibold uppercase tracking-wide text-gray-600 border-b border-gray-200">
              <div className="p-4 col-span-1 min-w-0">Name</div>
              <div className="p-4 col-span-1 min-w-0">Phone number</div>
              <div className="p-4 col-span-1 min-w-0">Email</div>
              <div className="p-4 col-span-1 min-w-0">Deck</div>
              <div className="p-4 col-span-1 min-w-0">Email sequence</div>
            </div>

            {loadingList ? (
              <div className="p-6 text-sm text-gray-500">Loading prospects…</div>
            ) : prospects.length === 0 ? (
              <div className="p-6 text-sm text-gray-500">No prospects yet. Add one to get started.</div>
            ) : (
              <ul>
                {prospects.map((p) => {
                  const deckState = deckByProspect[p.id] || { status: "idle" as const };
                  const emailState = emailsByProspect[p.id] || { status: "idle" as const };

                  return (
                    <li key={p.id} className="grid grid-cols-5 border-b border-gray-100">
                      <div className="p-4 col-span-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <div className="flex-1 min-w-0">
                            <div className="font-medium text-gray-900 truncate">{p.company_name}</div>
                            {p.contact_name && <div className="text-xs text-gray-500 truncate">{p.contact_name}</div>}
                          </div>
                          <button
                            onClick={() => handleEditProspect(p)}
                            className="ml-2 p-1 text-gray-400 hover:text-gray-600 transition-colors"
                            title="Edit prospect"
                          >
                            ⋯
                          </button>
                        </div>
                      </div>
                      <div className="p-4 col-span-1 text-sm text-gray-700 min-w-0 truncate">{p.phone_number || "-"}</div>
                      <div className="p-4 col-span-1 text-sm text-gray-700 truncate" title={p.email || "-"}>{p.email || "-"}</div>

                      {/* Deck column */}
                      <div className="p-4 col-span-1 min-w-0">
                        {deckState.status === "idle" && (
                          <button
                            onClick={() => handleGenerateDeck(p)}
                            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50 transition-colors"
                          >
                            Generate
                          </button>
                        )}
                        {deckState.status === "loading" && (
                          <div className="flex items-center gap-2 text-sm text-gray-500">
                            <div className="w-4 h-4 border-2 border-gray-300 border-t-[#f5f5dc] rounded-full animate-spin"></div>
                            Generating…
                          </div>
                        )}
                        {deckState.status === "ready" && deckState.deck && (
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => handleOpenDeck(deckState.deck!)}
                              className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50 transition-colors"
                            >
                              Open
                            </button>
                            <button
                              onClick={() => handleOpenDeck(deckState.deck!)}
                              className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm hover:bg-gray-50 transition-colors"
                              title="Edit"
                            >
                              ✏️
                            </button>
                            <button
                              onClick={() => handleRenderAndDownload(p)}
                              className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm hover:bg-gray-50 transition-colors"
                              title="View PDF"
                            >
                              👁️
                            </button>
                          </div>
                        )}
                      </div>

                      {/* Email sequence column */}
                      <div className="p-4 col-span-1 min-w-0">
                        {emailState.status === "idle" && (
                          <button
                            onClick={() => handleGenerateEmails(p)}
                            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50 transition-colors"
                          >
                            Generate
                          </button>
                        )}
                        {emailState.status === "loading" && (
                          <div className="flex items-center gap-2 text-sm text-gray-500">
                            <div className="w-4 h-4 border-2 border-gray-300 border-t-[#f5f5dc] rounded-full animate-spin"></div>
                            Generating…
                          </div>
                        )}
                        {emailState.status === "ready" && emailState.batch && (
                          <div className="flex flex-col gap-2 max-w-full">
                            {emailState.batch.items
                              .sort((a, b) => a.sequence_index - b.sequence_index)
                              .map((item) => {
                                const isSent = sentEmails.has(item.id);
                                const emailLabels = ["Intro", "Case Study", "Act Now"];
                                const emailLabel = emailLabels[item.sequence_index - 1] || `Email ${item.sequence_index}`;
                                return (
                                  <div key={item.id} className="flex items-center gap-2">
                                    <button
                                      onClick={() => handleOpenEmail(item)}
                                      className="flex-1 text-left px-3 py-2 rounded-lg border border-gray-300 hover:bg-gray-50 text-sm truncate transition-colors"
                                      title={`${emailLabel}: ${item.subject}`}
                                    >
                                      {emailLabel}
                                    </button>
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        toggleEmailSent(item.id);
                                      }}
                                      className={`flex items-center justify-center w-6 h-6 rounded-full border text-xs transition-colors ${
                                        isSent 
                                          ? "bg-[#f5f5dc] text-gray-700 border-[#f5f5dc]" 
                                          : "bg-white text-gray-400 border-gray-300 hover:border-[#f5f5dc]"
                                      }`}
                                      title={isSent ? "Mark as unsent" : "Mark as sent"}
                                    >
                                      {isSent ? "✓" : "○"}
                                    </button>
                                  </div>
                                );
                              })}
                          </div>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>

        {/* Right-side content panel */}
        <div className="col-span-4">
          <div className="rounded-xl border border-gray-200 bg-white p-6 h-[620px] overflow-auto shadow-sm">
            {!rightPanelContent && (
              <div className="text-sm text-gray-500">Click on a deck or email to view and edit.</div>
            )}
            {rightPanelContent === "deck" && selectedDeck && (
              <DeckEditor
                deck={selectedDeck}
                onSave={async (payload: { title?: string; slides: any[] }) => {
                  try {
                    const updated = await api.updateDeck(selectedDeck.id, payload);
                    // Update the deck in state
                    setDeckByProspect((m) => {
                      const owner = Object.keys(m).find((pid) =>
                        m[+pid]?.deck?.id === selectedDeck.id
                      );
                      if (!owner) return m;
                      return { ...m, [+owner]: { ...m[+owner], deck: updated } };
                    });
                    // Update the selected deck
                    setSelectedDeck(updated);
                  } catch (e: any) {
                    alert(`Failed to save deck: ${e?.message || "Unknown error"}`);
                  }
                }}
              />
            )}
            {rightPanelContent === "email" && selectedEmail && (
              <EmailEditor
                email={selectedEmail}
                onSave={async (payload) => {
                  try {
                    const updated = await api.updateEmail(selectedEmail.id, payload);
                    // Update the email in state
                    setEmailsByProspect((m) => {
                      const owner = Object.keys(m).find((pid) =>
                        m[+pid]?.batch?.items.some((i) => i.id === selectedEmail.id)
                      );
                      if (!owner) return m;
                      const es = m[+owner];
                      if (!es?.batch) return m;
                      const items = es.batch.items.map((i) => (i.id === updated.id ? updated : i));
                      return { ...m, [+owner]: { ...es, batch: { items } } };
                    });
                    // Update the selected email
                    setSelectedEmail(updated);
                  } catch (e: any) {
                    alert(`Failed to save email: ${e?.message || "Unknown error"}`);
                  }
                }}
              />
            )}
          </div>
        </div>
      </div>

      {/* Prospect modal */}
      {showModal && (
        <div className="fixed inset-0 z-20 grid place-items-center bg-black/40 p-4" onClick={() => setShowModal(false)}>
          <div
            className="w-full max-w-2xl rounded-xl border border-gray-200 bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-semibold text-gray-900">New Prospect</h3>
              <button onClick={() => setShowModal(false)} className="text-sm text-gray-500 hover:text-gray-700">✕</button>
            </div>

            <div className="grid grid-cols-2 gap-4">
              {[
                ["company_name", "Company name*"],
                ["contact_name", "Contact name"],
                ["email", "Email"],
                ["phone_number", "Phone number"],
                ["industry", "Industry"],
                ["revenue_range", "Revenue range"],
                ["location", "Location"],
                ["sale_motivation", "Sale motivation"],
                ["signals", "Signals"],
              ].map(([key, label]) => (
                <label key={key} className="text-sm">
                  <div className="mb-2 text-gray-600 font-medium">{label}</div>
                                      <input
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#f5f5dc] focus:border-transparent"
                      value={(form as any)[key] || ""}
                      onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                    />
                </label>
              ))}
              <label className="col-span-2 text-sm">
                <div className="mb-2 text-gray-600 font-medium">Notes</div>
                <textarea
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#f5f5dc] focus:border-transparent"
                  rows={3}
                  value={form.notes || ""}
                  onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                />
              </label>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => setShowModal(false)} className="btn-secondary">
                Cancel
              </button>
              <button onClick={handleCreateProspect} className="btn-primary">
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Prospect modal */}
      {showEditModal && editingProspect && (
        <div className="fixed inset-0 z-20 grid place-items-center bg-black/40 p-4" onClick={() => setShowEditModal(false)}>
          <div
            className="w-full max-w-2xl rounded-xl border border-gray-200 bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-semibold text-gray-900">Edit Prospect</h3>
              <button onClick={() => setShowEditModal(false)} className="text-sm text-gray-500 hover:text-gray-700">✕</button>
            </div>

            <div className="grid grid-cols-2 gap-4">
              {[
                ["company_name", "Company name*"],
                ["contact_name", "Contact name"],
                ["email", "Email"],
                ["phone_number", "Phone number"],
                ["industry", "Industry"],
                ["revenue_range", "Revenue range"],
                ["location", "Location"],
                ["sale_motivation", "Sale motivation"],
                ["signals", "Signals"],
              ].map(([key, label]) => (
                <label key={key} className="text-sm">
                  <div className="mb-2 text-gray-600 font-medium">{label}</div>
                  <input
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#f5f5dc] focus:border-transparent"
                    value={(form as any)[key] || ""}
                    onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                  />
                </label>
              ))}
              <label className="col-span-2 text-sm">
                <div className="mb-2 text-gray-600 font-medium">Notes</div>
                <textarea
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#f5f5dc] focus:border-transparent"
                  rows={3}
                  value={form.notes || ""}
                  onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                />
              </label>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => setShowEditModal(false)} className="btn-secondary">
                Cancel
              </button>
              <button onClick={handleUpdateProspect} className="btn-primary">
                Update
              </button>
            </div>
          </div>
        </div>
      )}

      {/* PDF Viewer Modal */}
      {showPdfViewer && pdfUrl && pdfViewMode === "modal" && (
        <div className="fixed inset-0 z-30 bg-black/40" onClick={() => setShowPdfViewer(false)}>
          <div className="absolute inset-4 bg-white rounded-xl overflow-hidden flex flex-col shadow-xl">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-gray-200">
              <h3 className="text-lg font-semibold text-gray-900">PDF Preview</h3>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPdfViewMode("split")}
                  className="btn-secondary"
                >
                  Split View
                </button>
                <button
                  onClick={() => window.open(pdfUrl, '_blank')}
                  className="btn-secondary"
                >
                  Open in New Tab
                </button>
                <button
                  onClick={() => setShowPdfViewer(false)}
                  className="text-sm text-gray-500 hover:text-gray-700"
                >
                  ✕
                </button>
              </div>
            </div>
            
            {/* PDF Content */}
            <div className="flex-1 overflow-hidden">
              <iframe
                src={pdfUrl}
                className="w-full h-full border-0"
                title="PDF Preview Yaya"
              />
            </div>
          </div>
        </div>
      )}

      {/* Split View PDF */}
      {showPdfViewer && pdfUrl && pdfViewMode === "split" && (
        <div className="fixed inset-0 z-30 bg-white">
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-gray-200 bg-white">
            <h3 className="text-lg font-semibold text-gray-900">Split View - PDF Preview</h3>
            <div className="flex items-center gap-2">
              <button
                onClick={handleRefreshPdf}
                className="btn-secondary"
                title="Refresh PDF after changes"
              >
                🔄 Refresh PDF
              </button>
              <button
                onClick={() => setPdfViewMode("modal")}
                className="btn-secondary"
              >
                Modal View
              </button>
              <button
                onClick={() => window.open(pdfUrl, '_blank')}
                className="btn-secondary"
              >
                Open in New Tab
              </button>
              <button
                onClick={() => setShowPdfViewer(false)}
                className="text-sm text-gray-500 hover:text-gray-700"
              >
                ✕
              </button>
            </div>
          </div>
          
          {/* Split Content */}
          <div className="flex h-[calc(100vh-80px)]">
            {/* Left side - Editor */}
            <div className="w-1/2 border-r border-gray-200 overflow-auto">
              <div className="p-4">
                <h4 className="text-md font-semibold mb-4 text-gray-900">Editor</h4>
                {rightPanelContent === "deck" && selectedDeck && (
                  <DeckEditor
                    deck={selectedDeck}
                    onSave={async (payload: { title?: string; slides: any[] }) => {
                      try {
                        const updated = await api.updateDeck(selectedDeck.id, payload);
                        // Update the deck in state
                        setDeckByProspect((m) => {
                          const owner = Object.keys(m).find((pid) =>
                            m[+pid]?.deck?.id === selectedDeck.id
                          );
                          if (!owner) return m;
                          return { ...m, [+owner]: { ...m[+owner], deck: updated } };
                        });
                        // Update the selected deck
                        setSelectedDeck(updated);
                      } catch (e: any) {
                        alert(`Failed to save deck: ${e?.message || "Unknown error"}`);
                      }
                    }}
                  />
                )}
                {rightPanelContent === "email" && selectedEmail && (
                  <EmailEditor
                    email={selectedEmail}
                    onSave={async (payload) => {
                      try {
                        const updated = await api.updateEmail(selectedEmail.id, payload);
                        // Update the email in state
                        setEmailsByProspect((m) => {
                          const owner = Object.keys(m).find((pid) =>
                            m[+pid]?.batch?.items.some((i) => i.id === selectedEmail.id)
                          );
                          if (!owner) return m;
                          const es = m[+owner];
                          if (!es?.batch) return m;
                          const items = es.batch.items.map((i) => (i.id === updated.id ? updated : i));
                          return { ...m, [+owner]: { ...es, batch: { items } } };
                        });
                        // Update the selected email
                        setSelectedEmail(updated);
                      } catch (e: any) {
                        alert(`Failed to save email: ${e?.message || "Unknown error"}`);
                      }
                    }}
                  />
                )}
              </div>
            </div>
            
            {/* Right side - PDF */}
            <div className="w-1/2">
              <iframe
                src={pdfUrl}
                className="w-full h-full border-0"
                title="PDF Preview"
              />
            </div>
          </div>
        </div>
      )}

    </main>
  );
}

function DeckEditor({
  deck,
  onSave,
}: {
  deck: Deck;
  onSave: (payload: { title?: string; slides: any[] }) => Promise<void>;
}) {
  const [title, setTitle] = useState(deck.title);
  const [slides, setSlides] = useState(deck.slides);
  const [saving, setSaving] = useState(false);
  const [aiEditing, setAiEditing] = useState<number | null>(null);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiLoading, setAiLoading] = useState(false);

  useEffect(() => {
    setTitle(deck.title);
    setSlides(deck.slides);
  }, [deck.id]);

  async function save() {
    setSaving(true);
    await onSave({ title, slides });
    setSaving(false);
  }

  async function handleAIEdit(slideIndex: number) {
    if (!aiPrompt.trim()) return;
    
    setAiLoading(true);
    try {
      console.log("AI Edit Request:", { deckId: deck.id, slideIndex, prompt: aiPrompt });
      const updated = await api.aiEditDeckSlide(deck.id, slideIndex, aiPrompt);
      console.log("AI Edit Response:", updated);
      setSlides(updated.slides);
      setAiEditing(null);
      setAiPrompt("");
      // Update the deck in the parent component
      await onSave({ title: updated.title, slides: updated.slides });
    } catch (e: any) {
      console.error("AI Edit Error:", e);
      alert(`AI editing failed: ${e?.message || "Unknown error"}`);
    } finally {
      setAiLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-gray-600">Deck Title</label>
        <input
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-base focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>

      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-gray-600">Slides</label>
        <div className="max-h-96 overflow-y-auto space-y-4">
          {slides.map((slide, index) => (
            <div key={index} className="border border-gray-200 rounded-lg p-4">
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium text-gray-600">Slide {index + 1} Title</label>
                  <button
                    onClick={() => setAiEditing(aiEditing === index ? null : index)}
                    className="text-xs px-2 py-1 rounded border border-gray-300 hover:bg-gray-50 transition-colors"
                  >
                    {aiEditing === index ? "Cancel AI Edit" : "AI Edit"}
                  </button>
                </div>
                
                {aiEditing === index ? (
                  <div className="space-y-2">
                    <textarea
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                      rows={2}
                      placeholder="Describe what changes you want the AI to make to this slide..."
                      value={aiPrompt}
                      onChange={(e) => setAiPrompt(e.target.value)}
                    />
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleAIEdit(index)}
                        disabled={aiLoading || !aiPrompt.trim()}
                        className="px-3 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 transition-colors"
                      >
                        {aiLoading ? "AI Editing..." : "Apply AI Changes"}
                      </button>
                      <button
                        onClick={() => {
                          setAiEditing(null);
                          setAiPrompt("");
                        }}
                        className="px-3 py-1 text-xs border border-gray-300 rounded hover:bg-gray-50 transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <input
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                    value={slide.title}
                    onChange={(e) => {
                      const newSlides = [...slides];
                      newSlides[index] = { ...slide, title: e.target.value };
                      setSlides(newSlides);
                    }}
                  />
                )}
                
                <label className="text-sm font-medium text-gray-600">Bullets</label>
                {aiEditing === index ? (
                  <div className="text-xs text-gray-500 p-2 bg-gray-50 rounded">
                    Use the AI edit feature above to modify bullets, or switch back to manual editing.
                  </div>
                ) : (
                  <textarea
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                    rows={3}
                    value={slide.bullets.join('\n')}
                    onChange={(e) => {
                      const newSlides = [...slides];
                      newSlides[index] = { 
                        ...slide, 
                        bullets: e.target.value.split('\n').filter(bullet => bullet.trim())
                      };
                      setSlides(newSlides);
                    }}
                    placeholder="Enter bullets, one per line"
                  />
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex justify-end">
        <button
          onClick={save}
          disabled={saving}
          className="btn-primary disabled:opacity-60"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}

function EmailEditor({
  email,
  onSave,
}: {
  email: EmailItem;
  onSave: (payload: { subject?: string; body?: string }) => Promise<void>;
}) {
  const [subject, setSubject] = useState(email.subject);
  const [body, setBody] = useState(email.body);
  const [saving, setSaving] = useState(false);
  const [aiEditing, setAiEditing] = useState(false);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiLoading, setAiLoading] = useState(false);

  useEffect(() => {
    setSubject(email.subject);
    setBody(email.body);
  }, [email.id]);

  async function save() {
    setSaving(true);
    await onSave({ subject, body });
    setSaving(false);
  }

  async function handleAIEdit() {
    if (!aiPrompt.trim()) return;
    
    setAiLoading(true);
    try {
      console.log("Email AI Edit Request:", { emailId: email.id, prompt: aiPrompt });
      const updated = await api.aiEditEmail(email.id, aiPrompt);
      console.log("Email AI Edit Response:", updated);
      setSubject(updated.subject);
      setBody(updated.body);
      setAiEditing(false);
      setAiPrompt("");
      // Update the email in the parent component
      await onSave({ subject: updated.subject, body: updated.body });
    } catch (e: any) {
      console.error("Email AI Edit Error:", e);
      alert(`AI editing failed: ${e?.message || "Unknown error"}`);
    } finally {
      setAiLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="text-xs font-semibold uppercase text-gray-500">
          {(() => {
            const emailLabels = ["Intro", "Case Study", "Act Now"];
            return emailLabels[email.sequence_index - 1] || `Email ${email.sequence_index}`;
          })()}
        </div>
        <button
          onClick={() => setAiEditing(!aiEditing)}
          className="text-xs px-2 py-1 rounded border border-gray-300 hover:bg-gray-50 transition-colors"
        >
          {aiEditing ? "Cancel AI Edit" : "AI Edit"}
        </button>
      </div>
      
      {aiEditing ? (
        <div className="space-y-3">
          <textarea
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
            rows={3}
            placeholder="Describe what changes you want the AI to make to this email..."
            value={aiPrompt}
            onChange={(e) => setAiPrompt(e.target.value)}
          />
          <div className="flex gap-2">
            <button
              onClick={handleAIEdit}
              disabled={aiLoading || !aiPrompt.trim()}
              className="px-3 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 transition-colors"
            >
              {aiLoading ? "AI Editing..." : "Apply AI Changes"}
            </button>
            <button
              onClick={() => {
                setAiEditing(false);
                setAiPrompt("");
              }}
              className="px-3 py-1 text-xs border border-gray-300 rounded hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
          </div>
          <div className="text-xs text-gray-500 p-2 bg-gray-50 rounded">
            AI editing mode: Describe your desired changes above, then click "Apply AI Changes" to update the email.
          </div>
        </div>
      ) : (
        <>
          <input
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-base focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
          />
          <textarea
            className="w-full rounded-lg border border-gray-300 px-3 py-2 min-h-[380px] focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
        </>
      )}
      
      <div className="flex justify-end">
        <button
          onClick={save}
          disabled={saving}
          className="btn-primary disabled:opacity-60"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
