import { useDropzone } from "react-dropzone";
import { UploadCloud, FileText } from "lucide-react";

// Drag-and-drop for PDFs. The actual upload endpoint is a Phase-2 backend
// addition; for the hackathon demo the primary path is DemoModeButton.
// This component still ships so the page looks complete.
export default function DropZone({ onFiles, disabled = false }) {
  const { getRootProps, getInputProps, isDragActive, acceptedFiles } = useDropzone({
    accept: { "application/pdf": [".pdf"] },
    onDrop: (files) => onFiles?.(files),
    disabled,
  });

  return (
    <div
      {...getRootProps()}
      className={`group relative flex flex-col items-center justify-center rounded-card border border-dashed px-8 py-14 text-center transition-all duration-200 ${
        disabled
          ? "border-border-light bg-cream-alt/40 cursor-not-allowed opacity-60"
          : isDragActive
          ? "border-ink bg-cream-alt"
          : "border-border-strong bg-cream-bg hover:bg-cream-alt"
      }`}
    >
      <input {...getInputProps()} />
      <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-full bg-ink text-cream-bg">
        <UploadCloud size={22} />
      </div>
      <p className="text-lg font-medium text-ink">
        {isDragActive ? "Drop PDFs to analyse" : "Drag & drop loan PDFs here"}
      </p>
      <p className="mt-1 text-sm text-ink-muted">
        Or click to browse · PDF only · 40-document max in demo build
      </p>

      {acceptedFiles.length > 0 && (
        <ul className="mt-6 flex w-full max-w-md flex-col gap-1.5 text-left">
          {acceptedFiles.slice(0, 5).map((f) => (
            <li
              key={f.path || f.name}
              className="flex items-center justify-between rounded-md border border-border-light bg-cream-alt/60 px-3 py-2 text-xs"
            >
              <span className="inline-flex items-center gap-2 text-ink">
                <FileText size={14} />
                <span className="truncate">{f.name}</span>
              </span>
              <span className="font-mono text-ink-muted">
                {(f.size / 1024).toFixed(1)} KB
              </span>
            </li>
          ))}
          {acceptedFiles.length > 5 && (
            <li className="px-3 py-1 text-xs text-ink-muted">
              + {acceptedFiles.length - 5} more
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
