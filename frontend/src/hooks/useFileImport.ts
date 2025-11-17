import { useState, useRef } from 'react';

interface UseFileImportProps {
  onFilesSelected: (files: File[]) => void;
  accept?: string;
  multiple?: boolean;
}

export function useFileImport({
  onFilesSelected,
  accept = '.pdf,.png,.jpg,.jpeg,.tif,.tiff',
  multiple = true,
}: UseFileImportProps) {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    if (files.length > 0) {
      onFilesSelected(files);
    }
    // Reset input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleDragOver = (event: React.DragEvent) => {
    event.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (event: React.DragEvent) => {
    event.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (event: React.DragEvent) => {
    event.preventDefault();
    setIsDragging(false);

    const files = Array.from(event.dataTransfer.files).filter(file => {
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();
      return accept.split(',').some(a => a.trim() === ext);
    });

    if (files.length > 0) {
      onFilesSelected(files);
    }
  };

  const openFilePicker = () => {
    fileInputRef.current?.click();
  };

  return {
    fileInputRef,
    isDragging,
    handleFileChange,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    openFilePicker,
    inputProps: {
      ref: fileInputRef,
      type: 'file' as const,
      accept,
      multiple,
      onChange: handleFileChange,
      style: { display: 'none' },
    },
  };
}
