'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, File as FileIcon, Globe, Server, Activity, Database, Folder as FolderIcon } from 'lucide-react';

interface Module {
  id: string;
  path: string;
  purpose: string;
  layer: "ui" | "api" | "service" | "data" | "shared";
}

interface LayerGroupProps {
  layer: Module["layer"];
  modules: Module[];
  onSelect: (m: Module) => void;
}

function layerIcon(layer: Module["layer"]) {
  const Icon = layer === "ui" ? Globe : 
               layer === "api" ? Server : 
               layer === "service" ? Activity : 
               layer === "data" ? Database : 
               FolderIcon;
  return <Icon size={16} className="text-white/80" />;
}

export default function LayerGroup({ layer, modules, onSelect }: LayerGroupProps) {
  const [open, setOpen] = useState(true);
  
  return (
    <div className="mb-2">
      <button 
        onClick={() => setOpen(v => !v)} 
        className="group flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left hover:bg-white/5"
      >
        <div className="flex items-center gap-2">
          {layerIcon(layer)}
          <div className="text-white/90 capitalize">{layer}</div>
        </div>
        <ChevronDown 
          size={16} 
          className={`transition-transform ${open ? "rotate-0" : "-rotate-90"} text-white/60`} 
        />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div 
            initial={{ height: 0, opacity: 0 }} 
            animate={{ height: "auto", opacity: 1 }} 
            exit={{ height: 0, opacity: 0 }} 
            className="ml-5 border-l border-white/10 pl-3"
          >
            {modules.length === 0 && (
              <div className="py-1 text-xs text-white/50">No modules</div>
            )}
            {modules.map(m => (
              <button 
                key={m.id} 
                onClick={() => onSelect(m)} 
                className="group mb-1 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-white/5"
              >
                <FileIcon size={16} className="text-white/70" />
                <div>
                  <div className="text-[13px] text-white/90">{m.path}</div>
                  <div className="text-xs text-white/50">{m.purpose}</div>
                </div>
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
