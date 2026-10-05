import esbuild from "esbuild";

await esbuild.build({
  entryPoints: ["src/extension.ts"],
  outfile: "dist/extension.cjs",
  bundle: true,
  platform: "node",
  format: "cjs",
  target: "node22",
  external: ["vscode"],
  sourcemap: false,
  legalComments: "none",
});

await esbuild.build({
  entryPoints: ["src/connector/cli.ts"],
  outfile: "../atlas-connector/atlas-connector.cjs",
  bundle: true, platform: "node", format: "cjs", target: "node22",
  sourcemap: false, legalComments: "none",
});
