"use client";

import { useRef, type ChangeEvent, type DragEvent, useState } from "react";
import { motion } from "framer-motion";
import { UploadCloud, FileText, X } from "lucide-react";

interface FileUploadProps {
  accept?: string;
  onFileSelect: (file: File) => void;
  file: File | null;
  onClear: () => void;
  hint?: string;
}

export default function FileUpload({
  accept = ".pdf,.csv",
  onFileSelect,
  file,
  onClear,
  hint = "Supports PDF and CSV files",
}: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) onFileSelect(selected);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) onFileSelect(dropped);
  };

  if (file) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="flex items-center gap-3 px-5 py-4 rounded-xl bg-secondary border border-border"
      >
        <FileText size={20} className="text-cyan-600 dark:text-cyan-400 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-sm truncate">{file.name}</p>
          <p className="text-xs text-muted-foreground">{(file.size / 1024).toFixed(1)} KB</p>
        </div>
        <button
          onClick={onClear}
          className="bg-transparent border-none p-1.5 text-muted-foreground hover:text-foreground cursor-pointer transition-colors"
        >
          <X size={16} />
        </button>
      </motion.div>
    );
  }

  return (
    <>
      <input ref={inputRef} type="file" accept={accept} onChange={handleChange} className="hidden" />
      <motion.div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        whileHover={{ borderColor: "rgb(8, 145, 178)" }} // Cyan-600 approx for hover
        className={`flex flex-col items-center justify-center py-10 px-6 rounded-xl border-2 border-dashed cursor-pointer transition-colors text-center ${
          dragOver 
            ? "border-cyan-500 bg-cyan-500/10" 
            : "border-border bg-secondary"
        }`}
      >
        <UploadCloud size={40} className="text-cyan-600 dark:text-cyan-400 mb-3 opacity-70" />
        <p className="font-semibold text-[0.95rem] mb-1">Click to browse or drag file here</p>
        <p className="text-sm text-muted-foreground">{hint}</p>
      </motion.div>
    </>
  );
}
