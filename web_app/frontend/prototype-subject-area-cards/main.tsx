// THROWAWAY prototype entry: the real Atlas app with sample data and a Cards / Current table switch.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createHashHistory } from "@tanstack/react-router";

import { createApiClient } from "../src/api";
import { WorkbenchApp, createWorkbenchRouter } from "../src/app";
import "../src/styles.css";
import "./cards.css";
import { LayoutSwitch } from "./layout";
import { sampleFetch } from "./sample-data";

const container = document.getElementById("root");
if (!container) throw new Error("Application root is missing.");

// Hash addresses keep every Atlas page inside this one prototype file.
if (!window.location.hash) window.location.hash = "/tenants/1/projects/1/subject-areas";
const router = createWorkbenchRouter({ api: createApiClient(sampleFetch), history: createHashHistory() });

createRoot(container).render(
  <StrictMode>
    <WorkbenchApp router={router} />
    <LayoutSwitch />
  </StrictMode>,
);
