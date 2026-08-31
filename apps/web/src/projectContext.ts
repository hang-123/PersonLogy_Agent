import type { ProjectContext } from "./types";

const PROJECT_CONTEXT_KEY = "personlogy.project-context";

const emptyContext: ProjectContext = {
  projectName: "",
  projectSlug: "",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function readProjectContext(): ProjectContext {
  try {
    const raw = window.localStorage.getItem(PROJECT_CONTEXT_KEY);
    if (!raw) return emptyContext;
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed)) return emptyContext;
    const projectName = typeof parsed.projectName === "string" ? parsed.projectName : "";
    const projectSlug = typeof parsed.projectSlug === "string" ? parsed.projectSlug : "";
    const projectId = typeof parsed.projectId === "string" ? parsed.projectId : undefined;
    return { projectName, projectSlug, projectId };
  } catch {
    return emptyContext;
  }
}

export function writeProjectContext(context: ProjectContext): void {
  window.localStorage.setItem(PROJECT_CONTEXT_KEY, JSON.stringify(context));
}

export function clearProjectContext(): void {
  window.localStorage.removeItem(PROJECT_CONTEXT_KEY);
}
