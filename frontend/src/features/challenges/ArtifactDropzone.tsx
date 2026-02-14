import { useRef, useState } from "react";

interface ArtifactDropzoneProps {
  disabled?: boolean;
  onFilesSelected: (files: File[]) => void;
}

export function ArtifactDropzone({ disabled = false, onFilesSelected }: ArtifactDropzoneProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const handleFiles = (files: FileList | null) => {
    if (!files || files.length === 0 || disabled) {
      return;
    }
    onFilesSelected(Array.from(files));
  };

  return (
    <div className="space-y-2">
      <div
        className={`rounded-lg border-2 border-dashed p-4 text-center text-sm ${
          isDragOver ? "border-accent bg-accentSoft/40" : "border-slate-300 bg-slate-50"
        } ${disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
        onClick={() => {
          if (!disabled) {
            inputRef.current?.click();
          }
        }}
        onDragOver={(event) => {
          if (disabled) {
            return;
          }
          event.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => {
          setIsDragOver(false);
        }}
        onDrop={(event) => {
          if (disabled) {
            return;
          }
          event.preventDefault();
          setIsDragOver(false);
          handleFiles(event.dataTransfer.files);
        }}
      >
        <p className="font-medium text-slate-700">Drag and drop challenge artifacts here</p>
        <p className="mt-1 text-xs text-slate-500">or click to browse files</p>
      </div>
      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(event) => {
          handleFiles(event.target.files);
          event.currentTarget.value = "";
        }}
      />
    </div>
  );
}
