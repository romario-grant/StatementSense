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
  multiple?: boolean;
  files?: File[];
  maxFiles?: number;
  onFilesSelect?: (files: File[]) => void;
}

export default function FileUpload({
  accept = ".pdf,.csv",
  onFileSelect,
  file,
  onClear,
  hint = "Supports PDF and CSV files",
  multiple = false,
  files = [],
  maxFiles = 3,
  onFilesSelect,
}: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(e.target.files || []);
    if (multiple && onFilesSelect) {
      onFilesSelect(selectedFiles.slice(0, maxFiles));
      return;
    }
    const selected = selectedFiles[0];
    if (selected) onFileSelect(selected);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const droppedFiles = Array.from(e.dataTransfer.files || []);
    if (multiple && onFilesSelect) {
      onFilesSelect(droppedFiles.slice(0, maxFiles));
      return;
    }
    const dropped = droppedFiles[0];
    if (dropped) onFileSelect(dropped);
  };

  if (multiple && files.length > 0) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="rounded-xl bg-secondary border border-border overflow-hidden"
      >
        <div className="divide-y divide-border">
          {files.map((selectedFile) => (
            <div key={`${selectedFile.name}-${selectedFile.size}`} className="flex items-center gap-3 px-5 py-3.5">
              <FileText size={20} className="text-foreground dark:text-foreground shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-sm truncate">{selectedFile.name}</p>
                <p className="text-xs text-muted-foreground">{(selectedFile.size / 1024).toFixed(1)} KB</p>
              </div>
            </div>
          ))}
        </div>
        <button
          onClick={onClear}
          className="w-full flex items-center justify-center gap-2 px-5 py-3 text-sm text-muted-foreground hover:text-foreground hover:bg-background/70 transition-colors border-t border-border"
        >
          <X size={16} />
          Clear files
        </button>
      </motion.div>
    );
  }

  if (file) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="flex items-center gap-3 px-5 py-4 rounded-xl bg-secondary border border-border"
      >
        <FileText size={20} className="text-foreground dark:text-foreground shrink-0" />
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
      <input ref={inputRef} type="file" accept={accept} multiple={multiple} onChange={handleChange} className="hidden" />
      <motion.div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        whileHover={{ borderColor: "hsl(var(--foreground))" }}
        className={`flex flex-col items-center justify-center py-10 px-6 rounded-xl border-2 border-dashed cursor-pointer transition-colors text-center ${
          dragOver 
            ? "border-border bg-primary/10" 
            : "border-border bg-secondary"
        }`}
      >
        <UploadCloud size={40} className="text-foreground dark:text-foreground mb-3 opacity-70" />
        <p className="font-semibold text-[0.95rem] mb-1">
          Click to browse or drag {multiple ? "files" : "file"} here
        </p>
        <p className="text-sm text-muted-foreground">{hint}</p>
      </motion.div>
    </>
  );
}
