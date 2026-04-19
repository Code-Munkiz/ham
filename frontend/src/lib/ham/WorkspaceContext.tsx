import * as React from 'react';

interface WorkspaceContextType {
  activeTask: string;
  setActiveTask: (task: string) => void;
  isControlPanelOpen: boolean;
  setIsControlPanelOpen: (isOpen: boolean) => void;
  workspaceName: string;
  branch: string;
  showContextBudget: boolean;
  setShowContextBudget: (show: boolean) => void;
  contextUsage: {
    used: number;
    total: number;
    breakdown: {
      instructions: number;
      git: number;
      tree: number;
      session: number;
    };
  };
}

const WorkspaceContext = React.createContext<WorkspaceContextType | undefined>(undefined);

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [activeTask, setActiveTask] = React.useState("REFINING THE WORKBENCH CORE ARCHITECTURE TO SUPPORT SPLIT-VIEW MODES.");
  const [isControlPanelOpen, setIsControlPanelOpen] = React.useState(false);
  const [showContextBudget, setShowContextBudget] = React.useState(true);

  // Rough heuristic-based estimates for the "premium cockpit" feel
  const contextUsage = {
    used: 48200,
    total: 200000,
    breakdown: {
      instructions: 12500,
      git: 15400,
      tree: 4800,
      session: 15500
    }
  };

  return (
    <WorkspaceContext.Provider value={{ 
      activeTask, 
      setActiveTask, 
      isControlPanelOpen, 
      setIsControlPanelOpen,
      workspaceName: "ham-workbench-v2",
      branch: "main",
      showContextBudget,
      setShowContextBudget,
      contextUsage
    }}>
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const context = React.useContext(WorkspaceContext);
  if (context === undefined) {
    throw new Error('useWorkspace must be used within a WorkspaceProvider');
  }
  return context;
}
