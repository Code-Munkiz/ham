export const BUILDER_FIRST_RUN_MICRO_LABEL = "Build with HAM";

export const BUILDER_FIRST_RUN_HEADLINE = "What do you want to build?";

export const BUILDER_FIRST_RUN_SUBHEADLINE = "Describe an app, website, dashboard, or tool.";

export const BUILDER_FIRST_RUN_PREVIEW_NOTE = "HAM will create a preview you can refine.";

export const BUILDER_WORKBENCH_EMPTY_TITLE = "Tell HAM what to build.";

export const BUILDER_WORKBENCH_EMPTY_SUBTITLE = "Your preview will appear here.";

export type BuilderExamplePrompt = {
  label: string;
  prompt: string;
};

export const BUILDER_EXAMPLE_PROMPTS: readonly BuilderExamplePrompt[] = [
  {
    label: "Newsletter landing page",
    prompt: "Build a landing page for my newsletter.",
  },
  {
    label: "Simple task tracker",
    prompt: "Create a simple task tracker.",
  },
  {
    label: "Portfolio with contact form",
    prompt: "Make a portfolio site with a contact form.",
  },
];

const FORBIDDEN_ONBOARDING_COPY =
  /\bconductor\b|\bcontrolplanerun\b|\bgcs\b|\brunner\b|safe_edit_low|provider routing|project_id/i;

export function builderOnboardingCopyLooksSafe(text: string): boolean {
  return !FORBIDDEN_ONBOARDING_COPY.test(text);
}
