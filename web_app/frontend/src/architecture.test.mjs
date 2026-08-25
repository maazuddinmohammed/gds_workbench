import { readdirSync, readFileSync } from "node:fs";
import { dirname, extname, isAbsolute, join, relative, resolve } from "node:path";

import ts from "typescript";
import { describe, expect, it } from "vitest";

const sourceRoot = resolve("src");
const featuresRoot = join(sourceRoot, "features");
const rootApiPath = join(sourceRoot, "api.ts");
const moduleExtensions = [".ts", ".tsx", ".js", ".jsx", ".mjs"];
const productionModules = listProductionModules(sourceRoot);
const productionModuleSet = new Set(productionModules);

describe("frontend Module architecture", () => {
  it("keeps production feature Modules independent from the root client", () => {
    const violations = productionModules
      .filter((filePath) => isWithin(filePath, featuresRoot))
      .flatMap((filePath) => resolvedRelativeImports(filePath)
        .filter(({ target }) => target === rootApiPath)
        .map(({ specifier }) => `${sourceName(filePath)} -> ${specifier}`));

    expect(violations).toEqual([]);
  });

  it("keeps core and shared Modules independent from feature Modules", () => {
    const inwardRoots = [join(sourceRoot, "core"), join(sourceRoot, "shared")];
    const violations = productionModules
      .filter((filePath) => inwardRoots.some((root) => isWithin(filePath, root)))
      .flatMap((filePath) => resolvedRelativeImports(filePath)
        .filter(({ target }) => isWithin(target, featuresRoot))
        .map(({ specifier }) => `${sourceName(filePath)} -> ${specifier}`));

    expect(violations).toEqual([]);
  });

  it("keeps the root client as re-exports, one aggregate Interface, and spread composition", () => {
    const sourceFile = parseModule(rootApiPath);
    const interfaces = sourceFile.statements.filter(ts.isInterfaceDeclaration);
    const functions = sourceFile.statements.filter(ts.isFunctionDeclaration);
    const unexpected = sourceFile.statements.filter((statement) => (
      !ts.isImportDeclaration(statement)
      && !ts.isExportDeclaration(statement)
      && !ts.isInterfaceDeclaration(statement)
      && !ts.isFunctionDeclaration(statement)
    ));

    expect(unexpected.map((statement) => ts.SyntaxKind[statement.kind])).toEqual([]);
    expect(interfaces.map((declaration) => declaration.name.text)).toEqual(["WorkbenchApi"]);
    expect(interfaces[0]?.members).toHaveLength(0);
    expect(functions.map((declaration) => declaration.name?.text)).toEqual(["createApiClient"]);

    const body = functions[0]?.body;
    expect(body?.statements).toHaveLength(2);
    const requestDeclaration = body?.statements[0];
    const clientReturn = body?.statements[1];
    expect(requestDeclaration && ts.isVariableStatement(requestDeclaration)).toBe(true);
    expect(clientReturn && ts.isReturnStatement(clientReturn)).toBe(true);

    if (!requestDeclaration || !ts.isVariableStatement(requestDeclaration)) return;
    if (!clientReturn || !ts.isReturnStatement(clientReturn)) return;
    const declarations = requestDeclaration.declarationList.declarations;
    expect(declarations).toHaveLength(1);
    expect(declarations[0]?.name.getText(sourceFile)).toBe("request");
    expect(declarations[0]?.initializer?.getText(sourceFile)).toBe("createHttpRequest(fetcher)");

    const expression = clientReturn.expression;
    expect(expression && ts.isObjectLiteralExpression(expression)).toBe(true);
    if (!expression || !ts.isObjectLiteralExpression(expression)) return;
    expect(expression.properties.every(ts.isSpreadAssignment)).toBe(true);
    const invalidComposition = expression.properties.flatMap((property) => {
      if (!ts.isSpreadAssignment(property)) return [property.getText(sourceFile)];
      const call = property.expression;
      if (!ts.isCallExpression(call)) return [property.getText(sourceFile)];
      const callText = call.getText(sourceFile);
      return /^create[A-Z][A-Za-z]+Api\(request\)$/.test(callText) ? [] : [callText];
    });
    expect(invalidComposition).toEqual([]);
  });

  it("keeps the production relative-import graph acyclic", () => {
    const graph = new Map(productionModules.map((filePath) => [
      filePath,
      [...new Set(resolvedRelativeImports(filePath).map(({ target }) => target))].sort(),
    ]));
    const cycle = findCycle(graph);

    expect(cycle?.map(sourceName) ?? []).toEqual([]);
  });
});

function listProductionModules(directory) {
  return readdirSync(directory, { withFileTypes: true })
    .sort((left, right) => left.name.localeCompare(right.name))
    .flatMap((entry) => {
      const filePath = join(directory, entry.name);
      if (entry.isDirectory()) {
        return entry.name === "test" ? [] : listProductionModules(filePath);
      }
      if (!moduleExtensions.includes(extname(entry.name))) return [];
      if (entry.name.includes(".test.") || entry.name.endsWith(".d.ts")) return [];
      return [filePath];
    });
}

function parseModule(filePath) {
  const extension = extname(filePath);
  const scriptKind = extension === ".tsx"
    ? ts.ScriptKind.TSX
    : extension === ".jsx"
      ? ts.ScriptKind.JSX
      : extension === ".ts"
        ? ts.ScriptKind.TS
        : ts.ScriptKind.JS;
  return ts.createSourceFile(
    filePath,
    readFileSync(filePath, "utf8"),
    ts.ScriptTarget.Latest,
    true,
    scriptKind,
  );
}

function resolvedRelativeImports(filePath) {
  return moduleSpecifiers(parseModule(filePath))
    .filter((specifier) => specifier.startsWith("."))
    .map((specifier) => ({ specifier, target: resolveModule(filePath, specifier) }))
    .filter(({ target }) => target !== null);
}

function moduleSpecifiers(sourceFile) {
  const specifiers = [];
  for (const statement of sourceFile.statements) {
    if (
      (ts.isImportDeclaration(statement) || ts.isExportDeclaration(statement))
      && statement.moduleSpecifier
      && ts.isStringLiteral(statement.moduleSpecifier)
    ) {
      specifiers.push(statement.moduleSpecifier.text);
    }
    if (
      ts.isImportEqualsDeclaration(statement)
      && ts.isExternalModuleReference(statement.moduleReference)
      && statement.moduleReference.expression
      && ts.isStringLiteral(statement.moduleReference.expression)
    ) {
      specifiers.push(statement.moduleReference.expression.text);
    }
  }
  const visit = (node) => {
    if (
      ts.isCallExpression(node)
      && node.expression.kind === ts.SyntaxKind.ImportKeyword
      && node.arguments[0]
      && ts.isStringLiteral(node.arguments[0])
    ) {
      specifiers.push(node.arguments[0].text);
    }
    ts.forEachChild(node, visit);
  };
  ts.forEachChild(sourceFile, visit);
  return specifiers;
}

function resolveModule(importer, specifier) {
  const basePath = resolve(dirname(importer), specifier);
  const baseExtension = extname(basePath);
  const candidates = baseExtension
    ? [
        basePath,
        ...(baseExtension === ".js" ? [basePath.slice(0, -3) + ".ts"] : []),
        ...(baseExtension === ".jsx" ? [basePath.slice(0, -4) + ".tsx"] : []),
      ]
    : [
        ...moduleExtensions.map((extension) => basePath + extension),
        ...moduleExtensions.map((extension) => join(basePath, `index${extension}`)),
      ];
  return candidates.find((candidate) => productionModuleSet.has(candidate)) ?? null;
}

function findCycle(graph) {
  const state = new Map();
  const stack = [];
  const stackIndex = new Map();
  let cycle = null;

  const visit = (modulePath) => {
    state.set(modulePath, "visiting");
    stackIndex.set(modulePath, stack.length);
    stack.push(modulePath);
    for (const dependency of graph.get(modulePath) ?? []) {
      if (!graph.has(dependency)) continue;
      if (state.get(dependency) === "visiting") {
        cycle = [...stack.slice(stackIndex.get(dependency)), dependency];
        return true;
      }
      if (state.get(dependency) !== "visited" && visit(dependency)) return true;
    }
    stack.pop();
    stackIndex.delete(modulePath);
    state.set(modulePath, "visited");
    return false;
  };

  for (const modulePath of [...graph.keys()].sort()) {
    if (!state.has(modulePath) && visit(modulePath)) break;
  }
  return cycle;
}

function isWithin(filePath, directory) {
  const pathFromDirectory = relative(directory, filePath);
  return pathFromDirectory !== ""
    && !pathFromDirectory.startsWith("..")
    && !isAbsolute(pathFromDirectory);
}

function sourceName(filePath) {
  return relative(sourceRoot, filePath).replaceAll("\\", "/");
}
