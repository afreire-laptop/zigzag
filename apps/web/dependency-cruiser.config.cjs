/** Import boundaries for the web app. Run with `pnpm boundaries`. */
module.exports = {
  forbidden: [
    { name: "no-circular", severity: "error", from: { path: "^src/" }, to: { circular: true } },
    {
      name: "browser-stays-inside-its-boundary",
      comment:
        "Outside src/, the browser may import packages and the generated client's public entry only: never backend " +
        "source, the OpenAPI file, or generated internals. Paths are relative to apps/web.",
      severity: "error",
      from: { path: "^src/" },
      to: {
        pathNot: "^(src/|node_modules/|\\.\\./\\.\\./node_modules/|\\.\\./\\.\\./packages/api-client/src/index\\.ts$)",
      },
    },
    {
      name: "no-node-builtins-in-the-browser",
      severity: "error",
      from: { path: "^src/" },
      to: { dependencyTypes: ["core"] },
    },
    {
      name: "design-system-stays-product-agnostic",
      severity: "error",
      from: { path: "^src/design-system/" },
      to: { path: "^src/(app|features|platform)/" },
    },
    {
      name: "platform-knows-no-ui",
      severity: "error",
      from: { path: "^src/platform/" },
      to: { path: "^src/(app|features|design-system)/" },
    },
    {
      name: "features-do-not-import-the-shell",
      severity: "error",
      from: { path: "^src/features/" },
      to: { path: "^src/app/" },
    },
    {
      name: "production-code-does-not-import-tests",
      severity: "error",
      from: { path: "^src/", pathNot: "\\.test\\.tsx?$|^src/test/" },
      to: { path: "^src/test/|\\.test\\.tsx?$" },
    },
  ],
  options: {
    doNotFollow: { path: "node_modules" },
    exclude: { path: "\\.css$" },
    tsConfig: { fileName: "tsconfig.json" },
    tsPreCompilationDeps: true,
    enhancedResolveOptions: { exportsFields: ["exports"], conditionNames: ["import", "default"] },
  },
};
