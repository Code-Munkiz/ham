import * as React from "react";

export const WorkspaceLibraryFlyoutContext = React.createContext<{
  openLibrary: () => void;
  toggleLibrary: () => void;
  libraryOpen: boolean;
} | null>(null);

export function useWorkspaceLibraryFlyout() {
  return React.useContext(WorkspaceLibraryFlyoutContext);
}
