// Test data typed by the generated contract, so a contract change breaks these tests at compile time.
import type { DecisionView, HandoffView, Operation, ProjectView, QuestionView, StatusView } from "@zigzag/api-client";
import { type Mocked, vi } from "vitest";
import { type Api, api } from "@/platform/api";

export const fixtureStatus: StatusView = {
  mode: "fixture",
  model: "fixture",
  reasoningEffort: null,
  promptVersion: null,
  fixtures: {
    briefs: [{ label: "Clear brief", text: "Clear brief text." }],
    replies: [{ label: "Short reply", text: "Coordination first." }],
  },
  damagedOperations: [],
};

export function question(overrides: Partial<QuestionView> = {}): QuestionView {
  return {
    id: "q1",
    text: "Which improvement should we investigate first?",
    status: "open",
    effect: "Changes whom we speak to.",
    basis: "The brief names no primary user.",
    sourceQuote: null,
    options: [
      {
        id: "q1.1",
        label: "Coordination during service",
        description: "How people respond during an incident.",
        tradeoff: "May add work during service.",
        establishes: [{ kind: "direction", label: "Direction to pursue", text: "Investigate coordination." }],
      },
      {
        id: "q1.2",
        label: "Owner visibility afterwards",
        description: "How owners follow up.",
        tradeoff: "Leaves coordination unchanged.",
        establishes: [{ kind: "direction", label: "Direction to pursue", text: "Investigate owner follow-up." }],
      },
    ],
    deferEffect: "Investigate both before choosing.",
    proposedBy: "fixture",
    resolution: null,
    actions: { select: true, answerInOwnWords: true, leaveOpen: true },
    ...overrides,
  };
}

export function decision(overrides: Partial<DecisionView> = {}): DecisionView {
  return {
    id: "d1",
    at: "2026-10-06T10:00:00.000Z",
    revision: 1,
    action: "brief",
    summary: "From your brief: recorded 1 statement in your words.",
    reason: null,
    inputId: "s1",
    supersededBy: null,
    partlySupersededBy: [],
    ...overrides,
  };
}

export function project(overrides: Partial<ProjectView> = {}): ProjectView {
  return {
    id: "p1",
    title: "Help independent restaurants deal with operational incidents.",
    revision: 1,
    status: "draft",
    createdAt: "2026-10-06T10:00:00.000Z",
    updatedAt: "2026-10-06T10:00:00.000Z",
    focusId: "q1",
    hasNextStep: false,
    openQuestionCount: 1,
    intent: [
      {
        kind: "outcome",
        label: "Desired outcome",
        items: [{ id: "i1", text: "Help restaurants with incidents.", basis: "From your brief: “Help restaurants”" }],
      },
      { kind: "audience", label: "Audience and circumstances", items: [] },
    ],
    questions: [question()],
    assumptions: [
      {
        id: "a1",
        text: "Restaurants struggle with incidents.",
        basis: "Agent inference.",
        effect: "Interviews can check this.",
        relied: false,
        proposedBy: "fixture",
      },
    ],
    needed: [{ id: "n1", text: "The release notes.", basis: "Named in your brief.", effect: "Needed later." }],
    decisions: [decision()],
    inputs: [
      { id: "s1", kind: "brief", text: "Help restaurants.", at: "2026-10-06T10:00:00.000Z", interpretedBy: "fixture" },
    ],
    ...overrides,
  };
}

export function operation(overrides: Partial<Operation> = {}): Operation {
  return {
    id: "op1",
    kind: "create",
    status: "queued",
    version: 1,
    projectId: null,
    baseRevision: null,
    questionId: null,
    text: "Brief.",
    createdAt: "2026-10-06T10:00:00.000Z",
    updatedAt: "2026-10-06T10:00:00.000Z",
    deadlineAt: "2026-10-06T10:03:00.000Z",
    result: null,
    error: null,
    modelCall: null,
    ...overrides,
  };
}

export function handoff(overrides: Partial<HandoffView> = {}): HandoffView {
  return {
    projectId: "p1",
    current: { revision: 1, status: "draft", markdown: "# Intent handoff: Title\n\n**Status: DRAFT.**\n", json: "{}" },
    lastReviewed: null,
    reviews: [],
    changes: null,
    ...overrides,
  };
}

/** Every API call is a typed mock; tests set the replies they need. URL builders are the real ones. */
export function fakeApi(): Mocked<Api> {
  return {
    status: vi.fn<Api["status"]>(),
    current: vi.fn<Api["current"]>(),
    project: vi.fn<Api["project"]>(),
    handoff: vi.fn<Api["handoff"]>(),
    create: vi.fn<Api["create"]>(),
    reply: vi.fn<Api["reply"]>(),
    assess: vi.fn<Api["assess"]>(),
    decide: vi.fn<Api["decide"]>(),
    review: vi.fn<Api["review"]>(),
    activeOperations: vi.fn<Api["activeOperations"]>(),
    operation: vi.fn<Api["operation"]>(),
    cancel: vi.fn<Api["cancel"]>(),
    exportUrl: vi.fn(api.exportUrl),
    eventsUrl: vi.fn(api.eventsUrl),
  };
}
