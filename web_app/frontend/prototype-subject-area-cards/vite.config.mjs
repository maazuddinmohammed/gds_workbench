// THROWAWAY: runs the real Atlas frontend with sample data and Subject Area cards.
// From the repository root:
//   node_modules/.bin/vite --config web_app/frontend/prototype-subject-area-cards/vite.config.mjs
// then open http://127.0.0.1:4331/prototype-subject-area-cards/
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const local = (path) => fileURLToPath(new URL(path, import.meta.url));

// The two production files that draw Subject Area tables are served from card versions here,
// so src/ stays untouched. Each copy keeps its original relative imports.
const swaps = new Map([
  [local("../src/features/subject_areas/SubjectAreasScreen.tsx"), local("./SubjectAreasScreen.tsx")],
  [local("../src/features/projects/ModelSubjectAreas.tsx"), local("./ModelSubjectAreas.tsx")],
]);

export default defineConfig({
  root: local(".."),
  plugins: [
    {
      name: "prototype-subject-area-cards",
      enforce: "pre",
      load(id) {
        const swap = swaps.get(id.split("?")[0]);
        if (!swap) return null;
        this.addWatchFile(swap);
        return readFileSync(swap, "utf8");
      },
    },
    react(),
  ],
  optimizeDeps: { entries: ["prototype-subject-area-cards/index.html"] },
  server: { host: "127.0.0.1", port: 4331, strictPort: true },
});
