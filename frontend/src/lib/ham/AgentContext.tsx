import * as React from 'react';
import { Agent } from './types';
import { MOCK_AGENTS } from './mocks';

interface AgentContextType {
  agents: Agent[];
  selectedAgentId: string | null;
  setSelectedAgentId: (id: string | null) => void;
  updateAgent: (id: string, updates: Partial<Agent>) => void;
  setAgents: React.Dispatch<React.SetStateAction<Agent[]>>;
}

const AgentContext = React.createContext<AgentContextType | undefined>(undefined);

export function AgentProvider({ children }: { children: React.ReactNode }) {
  const [agents, setAgents] = React.useState<Agent[]>(MOCK_AGENTS);
  const [selectedAgentId, setSelectedAgentId] = React.useState<string | null>(null);

  const updateAgent = (id: string, updates: Partial<Agent>) => {
    setAgents(prev => prev.map(a => a.id === id ? { ...a, ...updates } : a));
  };

  return (
    <AgentContext.Provider value={{ agents, selectedAgentId, setSelectedAgentId, updateAgent, setAgents }}>
      {children}
    </AgentContext.Provider>
  );
}

export function useAgent() {
  const context = React.useContext(AgentContext);
  if (context === undefined) {
    throw new Error('useAgent must be used within an AgentProvider');
  }
  return context;
}
