import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { createApiClient } from "./api";
import { AtlasPlatformApp, createAtlasPlatformRouter } from "./app";
import "./styles.css";

const container = document.getElementById("root");

if (!container) throw new Error("Application root is missing.");

const router = createAtlasPlatformRouter({ api: createApiClient() });

createRoot(container).render(
  <StrictMode>
    <AtlasPlatformApp router={router} />
  </StrictMode>,
);
