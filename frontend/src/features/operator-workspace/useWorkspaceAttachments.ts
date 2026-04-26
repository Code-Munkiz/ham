import * as React from "react";

type UseWorkspaceAttachmentsOptions = {
  onSelectFile: (file: File) => void;
};

export function useWorkspaceAttachments({
  onSelectFile,
}: UseWorkspaceAttachmentsOptions) {
  const inputRef = React.useRef<HTMLInputElement | null>(null);
  const [isDraggingOver, setIsDraggingOver] = React.useState(false);

  const openPicker = React.useCallback(() => {
    inputRef.current?.click();
  }, []);

  const onInputChange = React.useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const list = event.target.files;
      event.target.value = "";
      const file = list?.[0];
      if (file) onSelectFile(file);
    },
    [onSelectFile],
  );

  const onDragOver = React.useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
  }, []);

  const onDragEnter = React.useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDraggingOver(true);
  }, []);

  const onDragLeave = React.useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDraggingOver(false);
  }, []);

  const onDrop = React.useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      event.stopPropagation();
      setIsDraggingOver(false);
      const file = event.dataTransfer?.files?.[0];
      if (file) onSelectFile(file);
    },
    [onSelectFile],
  );

  return {
    inputRef,
    isDraggingOver,
    openPicker,
    onInputChange,
    onDragOver,
    onDragEnter,
    onDragLeave,
    onDrop,
  };
}

