import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { createApiClient } from "./api";
import { WorkbenchApp, createWorkbenchRouter } from "./app";
import "./styles.css";

const container = document.getElementById("root");

if (!container) throw new Error("Application root is missing.");

const router = createWorkbenchRouter({ api: createApiClient() });

createRoot(container).render(
  <StrictMode>
    <WorkbenchApp router={router} />
  </StrictMode>,
);
