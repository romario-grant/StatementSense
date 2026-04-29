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
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.75rem",
          padding: "1rem 1.25rem",
          borderRadius: "12px",
          background: "var(--bg-secondary)",
          border: "1px solid var(--border-default)",
        }}
      >
        <FileText size={20} style={{ color: "var(--accent-teal)", flexShrink: 0 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ fontWeight: 600, fontSize: "0.9rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{file.name}</p>
          <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>{(file.size / 1024).toFixed(1)} KB</p>
        </div>
        <button
          onClick={onClear}
          style={{
            background: "none",
            border: "none",
            padding: "0.3rem",
            color: "var(--text-muted)",
            cursor: "pointer",
          }}
        >
          <X size={16} />
        </button>
      </motion.div>
    );
  }

  return (
    <>
      <input ref={inputRef} type="file" accept={accept} onChange={handleChange} style={{ display: "none" }} />
      <motion.div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        whileHover={{ borderColor: "var(--accent-teal)" }}
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "2.5rem 1.5rem",
          borderRadius: "14px",
          border: `1.5px dashed ${dragOver ? "var(--accent-teal)" : "var(--border-default)"}`,
          background: dragOver ? "var(--accent-teal-light)" : "var(--bg-secondary)",
          cursor: "pointer",
          transition: "background 0.2s ease",
          textAlign: "center",
        }}
      >
        <UploadCloud size={40} style={{ color: "var(--accent-teal)", marginBottom: "0.75rem", opacity: 0.7 }} />
        <p style={{ fontWeight: 600, fontSize: "0.95rem", marginBottom: "0.3rem" }}>Click to browse or drag file here</p>
        <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>{hint}</p>
      </motion.div>
    </>
  );
}
