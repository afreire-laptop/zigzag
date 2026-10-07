import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "@/app/App";
import type { WorkspaceDeps } from "@/features/workspace/use-workspace";
import { api } from "@/platform/api";
import "./styles/index.css";

// Created once: the workspace hook's effects depend on these identities.
const deps: WorkspaceDeps = { api, watch: { openStream: (url) => new EventSource(url) } };

const root = document.getElementById("root");
if (!root) throw new Error("The page has no #root element.");
createRoot(root).render(
  <StrictMode>
    <App deps={deps} />
  </StrictMode>,
);
