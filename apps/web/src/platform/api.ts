// The browser's only way to the API: the generated SDK, called on the page's own origin.
// Responses are validated by the generated Zod schemas; failures become a typed RequestFailed.
import {
  type CurrentProjectView,
  cancelOperation,
  createAssessment,
  createDecision,
  createProject,
  createReply,
  createReview,
  type DeferCommand,
  type EditCommand,
  getCurrentProject,
  getHandoff,
  getOperation,
  getProject,
  getStatus,
  type HandoffView,
  listActiveOperations,
  type Operation,
  type ProjectView,
  type RelyCommand,
  type RemoveCommand,
  type SelectCommand,
  type StatusView,
  zProblem,
} from "@intent-harness/api-client";

export type Failure = {
  message: string;
  kind: string;
  retryable: boolean;
  issues: readonly string[];
  activeOperationId: string | null;
};

export class RequestFailed extends Error {
  readonly failure: Failure;

  constructor(failure: Failure) {
    super(failure.message);
    this.failure = failure;
  }
}

type Result<T> = { data?: T; error?: unknown; response?: Response };

export function toFailure(error: unknown, status?: number): Failure {
  const problem = zProblem.safeParse(error);
  if (problem.success) {
    const p = problem.data;
    return {
      message: p.detail,
      kind: p.kind,
      retryable: p.retryable,
      issues: p.issues ?? [],
      activeOperationId: p.activeOperationId ?? null,
    };
  }
  if (error instanceof TypeError) {
    return {
      message: "Could not reach the local server. Check that it is running, then retry.",
      kind: "network",
      retryable: true,
      issues: [],
      activeOperationId: null,
    };
  }
  return {
    message: status ? `The server answered ${status}.` : "The server's response could not be read.",
    kind: "server",
    retryable: true,
    issues: [],
    activeOperationId: null,
  };
}

async function call<T>(request: () => Promise<Result<T>>): Promise<T> {
  let result: Result<T>;
  try {
    result = await request();
  } catch (error) {
    throw new RequestFailed(toFailure(error));
  }
  if (result.error !== undefined || result.data === undefined) {
    throw new RequestFailed(toFailure(result.error, result.response?.status));
  }
  return result.data;
}

export type DecisionCommand = SelectCommand | DeferCommand | EditCommand | RemoveCommand | RelyCommand;
type WithoutRevision<T> = T extends unknown ? Omit<T, "baseRevision"> : never;
export type Decide = WithoutRevision<DecisionCommand>;

const project = (projectId: string) => ({ path: { project_id: projectId } });
const operation = (operationId: string) => ({ path: { operation_id: operationId } });

export const api = {
  status: (): Promise<StatusView> => call(() => getStatus()),
  current: (): Promise<CurrentProjectView> => call(() => getCurrentProject()),
  project: (projectId: string): Promise<ProjectView> => call(() => getProject(project(projectId))),
  handoff: (projectId: string): Promise<HandoffView> => call(() => getHandoff(project(projectId))),
  create: (brief: string): Promise<Operation> => call(() => createProject({ body: { brief } })),
  reply: (p: ProjectView, text: string, questionId: string | null): Promise<Operation> =>
    call(() => createReply({ ...project(p.id), body: { text, questionId, baseRevision: p.revision } })),
  assess: (p: ProjectView): Promise<Operation> =>
    call(() => createAssessment({ ...project(p.id), body: { baseRevision: p.revision } })),
  decide: (p: ProjectView, command: Decide): Promise<ProjectView> =>
    call(() => createDecision({ ...project(p.id), body: { ...command, baseRevision: p.revision } as DecisionCommand })),
  review: (p: ProjectView): Promise<ProjectView> =>
    call(() => createReview({ ...project(p.id), body: { revision: p.revision } })),
  activeOperations: (): Promise<Operation[]> => call(() => listActiveOperations()),
  operation: (operationId: string): Promise<Operation> => call(() => getOperation(operation(operationId))),
  cancel: (operationId: string): Promise<Operation> => call(() => cancelOperation(operation(operationId))),
  exportUrl: (projectId: string, format: "markdown" | "json", revision?: number): string =>
    `/api/projects/${projectId}/exports/${format}${revision === undefined ? "" : `?revision=${revision}`}`,
  eventsUrl: (operationId: string): string => `/api/operations/${operationId}/events`,
};

export type Api = typeof api;
