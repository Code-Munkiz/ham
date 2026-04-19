import { Agent } from "./types";

export const DROID_TEMPLATES: Partial<Agent>[] = [
  {
    name: "Builder",
    role: "Code development, refactoring, implementation",
    description: "Specializes in high-quality architecture and logic execution.",
    assignedTools: ["Git Inspector", "File System", "Code Parser"],
    model: "Claude 3.5 Sonnet",
    provider: "Anthropic",
    traits: ["methodical", "clean code", "efficient"],
    communicationStyle: "Technical & Precise",
  },
  {
    name: "Reviewer",
    role: "Code quality, security audit, review",
    description: "Expert at finding vulnerabilities and style inconsistencies.",
    assignedTools: ["Git Inspector", "Code Parser"],
    model: "GPT-4o",
    provider: "OpenAI",
    traits: ["meticulous", "critical", "security-focused"],
    communicationStyle: "Minimal / Terse",
  },
  {
    name: "Researcher",
    role: "Documentation, technical search, knowledge",
    description: "Connects the workbench to the sum of human technical knowledge.",
    assignedTools: ["Web Browser", "File System"],
    model: "Perplexity Pro",
    provider: "Perplexity",
    traits: ["thorough", "curious", "factual"],
    communicationStyle: "Detailed & Educational",
  },
  {
    name: "Coordinator",
    role: "Task decomposition, planning, delegation",
    description: "Orchestrates complex multi-step missions across the workforce.",
    assignedTools: ["File System"],
    model: "Claude 3.5 Sonnet",
    provider: "Anthropic",
    traits: ["organized", "strategic", "clear"],
    communicationStyle: "Conversational",
  },
  {
    name: "QA",
    role: "Test generation, validation, coverage",
    description: "Ensures nothing ships without verified binary success.",
    assignedTools: ["File System", "Code Parser", "Terminal"],
    model: "GPT-4o",
    provider: "OpenAI",
    traits: ["skeptical", "edge-case-obsessed", "precise"],
    communicationStyle: "Technical & Precise",
  }
];

export const AVAILABLE_MODELS = [
  "Claude 3.5 Sonnet",
  "Claude 3 Opus",
  "GPT-4o",
  "GPT-4 Turbo",
  "Perplexity Pro",
  "Llama 3 70B"
];

export const AVAILABLE_PROVIDERS = [
  "Anthropic",
  "OpenAI",
  "Perplexity",
  "Local/Ollama"
];

export const ALL_TOOLS = [
  { name: "Git Inspector", icon: "GitBranch" },
  { name: "File System", icon: "FileCode" },
  { name: "Code Parser", icon: "Code2" },
  { name: "Web Browser", icon: "Globe" },
  { name: "Terminal", icon: "Terminal" },
  { name: "Image Generation", icon: "Image" }
];
