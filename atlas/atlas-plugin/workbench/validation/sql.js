(function (root, factory) {
  "use strict";
  const node = typeof module === "object" && module.exports;
  const api = factory(node ? require("../core.js") : root.GDSCore);
  if (node) module.exports = api;
  root.AtlasSql = api;
})(globalThis, function (core) {
  "use strict";
  function splitSql(sql) {
    const statements = [];
    let start = 0;
    let quote = null;
    let lineComment = false;
    let blockComment = false;
    for (let index = 0; index < sql.length; index += 1) {
      const character = sql[index];
      const next = sql[index + 1];
      if (lineComment) {
        if (character === "\n") lineComment = false;
      } else if (blockComment) {
        if (character === "*" && next === "/") {
          blockComment = false;
          index += 1;
        }
      } else if (quote) {
        if (character === quote && sql[index + 1] === quote) index += 1;
        else if (character === quote) quote = null;
      } else if (character === "-" && next === "-") {
        lineComment = true;
        index += 1;
      } else if (character === "/" && next === "*") {
        blockComment = true;
        index += 1;
      } else if (["'", '"', "`"].includes(character)) quote = character;
      else if (character === ";") {
        const value = sql.slice(start, index).trim();
        if (value) statements.push(value);
        start = index + 1;
      }
    }
    const final = sql.slice(start).trim();
    if (final) statements.push(final);
    return quote || blockComment ? null : statements;
  }

  function maskSql(sql) {
    let result = "";
    let quote = null;
    let lineComment = false;
    let blockComment = false;
    for (let index = 0; index < sql.length; index += 1) {
      const character = sql[index];
      const next = sql[index + 1];
      if (lineComment) {
        result += character === "\n" ? "\n" : " ";
        if (character === "\n") lineComment = false;
      } else if (blockComment) {
        result += " ";
        if (character === "*" && next === "/") {
          result += " ";
          blockComment = false;
          index += 1;
        }
      } else if (quote === "'") {
        result += " ";
        if (character === "'" && next === "'") {
          result += " ";
          index += 1;
        } else if (character === "'") quote = null;
      } else if (quote) {
        result += character;
        if (character === quote && next === quote) {
          result += next;
          index += 1;
        } else if (character === quote) quote = null;
      } else if (character === "-" && next === "-") {
        result += "  ";
        lineComment = true;
        index += 1;
      } else if (character === "/" && next === "*") {
        result += "  ";
        blockComment = true;
        index += 1;
      } else {
        result += character;
        if (["'", '"', "`"].includes(character)) quote = character;
      }
    }
    return result;
  }

  function unquoteIdentifier(value) {
    if ((value.startsWith("`") && value.endsWith("`")) ||
        (value.startsWith('"') && value.endsWith('"'))) return value.slice(1, -1);
    return value;
  }

  function identifierParts(value) {
    const parts = [];
    let start = 0;
    let quote = null;
    for (let index = 0; index < value.length; index += 1) {
      const character = value[index];
      if (quote) {
        if (character === quote) quote = null;
      } else if (["`", '"'].includes(character)) quote = character;
      else if (character === ".") {
        parts.push(unquoteIdentifier(value.slice(start, index)).toLowerCase());
        start = index + 1;
      }
    }
    parts.push(unquoteIdentifier(value.slice(start)).toLowerCase());
    return parts;
  }

  function identifierKey(value) { return core.stableStringify(identifierParts(value)); }

  function physicalRelationsAreSafe(sql, temporaryRelations, qualification = 3) {
    const masked = maskSql(sql);
    if (/\b(?:from|join)\s*(?:$|where\b|group\b|order\b|having\b|limit\b)/i.test(masked)) {
      return false;
    }
    const localRelations = new Set(temporaryRelations);
    const cte = /(?:\bwith\b|,)\s*(`[^`]+`|"[^"]+"|[A-Za-z_][\w$]*)\s+as\s*\(/gi;
    for (const match of masked.matchAll(cte)) localRelations.add(identifierKey(match[1]));
    // Track each parenthesis level so comma-joined inputs are checked too; SELECT
    // columns, CTE separators and function arguments are not relation separators.
    const tokens = [...masked.matchAll(/`(?:``|[^`])+`|"(?:""|[^"])+"|[A-Za-z_][\w$]*|[(),.]/g)];
    const fromAtDepth = new Map(); let depth = 0;
    for (let index = 0; index < tokens.length; index++) {
      const token = tokens[index][0], keyword = token.toLowerCase();
      if (token === "(") { depth++; fromAtDepth.delete(depth); continue; }
      if (token === ")") { fromAtDepth.delete(depth); depth--; continue; }
      if (["select", "where", "group", "order", "having", "qualify", "limit", "union", "intersect", "except"].includes(keyword)) fromAtDepth.delete(depth);
      if (keyword !== "from" && keyword !== "join" && !(token === "," && fromAtDepth.get(depth))) continue;
      fromAtDepth.set(depth, true);
      const tail = masked.slice(tokens[index].index + token.length).trimStart();
      if (tail.startsWith("(")) continue; // Nested query is visited by the same scan.
      const relation = /^((?:`(?:``|[^`])+`|"(?:""|[^"])+"|[A-Za-z_][\w$]*)(?:\s*\.\s*(?:`(?:``|[^`])+`|"(?:""|[^"])+"|[A-Za-z_][\w$]*))*)/.exec(tail);
      if (!relation) return false;
      const name = relation[1].replace(/\s*\.\s*/g, ".");
      if (tail.slice(relation[0].length).trimStart().startsWith("(")) continue;
      if (identifierParts(name).length !== qualification && !localRelations.has(identifierKey(name))) return false;
    }
    const described = /\bdescribe(?:\s+table)?\s+((?:`[^`]+`|"[^"]+"|[A-Za-z_][\w$]*)(?:\.(?:`[^`]+`|"[^"]+"|[A-Za-z_][\w$]*)){0,2})/i.exec(masked);
    return !described || identifierParts(described[1]).length === qualification;
  }

  function validateReadSql(sql) {
    if (typeof sql !== "string") return { valid: false, finalReturnsRows: false };
    const statements = splitSql(sql);
    if (!statements || !statements.length || statements.length > 25) {
      return { valid: false, finalReturnsRows: false };
    }
    const temporaryRelations = new Set();
    let finalReturnsRows = false;
    for (const statement of statements) {
      const masked = maskSql(statement).trim();
      const rowReturning = /^(select|with|values|describe|show)\b/i.test(masked);
      if (/\b(secret|try_secret)\s*\(/i.test(masked) ||
          /\b(insert|update|delete|merge|drop|alter|truncate|copy|grant|revoke|call|execute|into)\b/i.test(masked)) {
        return { valid: false, finalReturnsRows: false };
      }
      if (rowReturning) {
        if (/^(select|with)\b/i.test(masked) &&
            (!physicalRelationsAreSafe(masked, temporaryRelations) ||
              (/^with\b/i.test(masked) && !/\bas\s*\(/i.test(masked)) ||
              /^select\s+from\b/i.test(masked))) {
          return { valid: false, finalReturnsRows: false };
        }
        if (/^describe\b/i.test(masked) && !physicalRelationsAreSafe(masked, temporaryRelations)) {
          return { valid: false, finalReturnsRows: false };
        }
        finalReturnsRows = true;
        continue;
      }
      const create = /^create\s+(?:or\s+replace\s+)?temp(?:orary)?\s+(view|table)\s+(`[^`]+`|"[^"]+"|[A-Za-z_][\w$]*)(?=\s|\(|$)([\s\S]*)$/i.exec(masked);
      if (!create || /\b(?:using|location|clone)\b/i.test(create[3])) {
        return { valid: false, finalReturnsRows: false };
      }
      const query = /^\s+as\s+([\s\S]+)$/i.exec(create[3]);
      if (create[1].toLowerCase() === "view" && !query) {
        return { valid: false, finalReturnsRows: false };
      }
      if (query && (!/^(select|with|values)\b/i.test(query[1].trim()) ||
          !physicalRelationsAreSafe(query[1], temporaryRelations))) {
        return { valid: false, finalReturnsRows: false };
      }
      temporaryRelations.add(identifierKey(create[2]));
      finalReturnsRows = false;
    }
    return { valid: true, finalReturnsRows };
  }


  // Token-aware outer projection: COUNT(*) and multiplication are expressions, not wildcard projections.
  function finalProjection(sql) {
    const masked = maskSql(sql), columns = [];
    let start = 0, depth = 0, quote = null, projecting = false;
    const finish = end => { columns.push(masked.slice(start, end).trim().replace(/^distinct\s+/i, "")); };
    for (let index = 0; index < masked.length; index++) {
      const char = masked[index];
      if (quote) { if (char === quote && masked[index + 1] === quote) index++; else if (char === quote) quote = null; continue; }
      if (["`", '"'].includes(char)) { quote = char; continue; }
      if (char === "(") depth++; else if (char === ")") depth--;
      if (depth !== 0) continue;
      const boundary = index === 0 || !/[A-Za-z0-9_]/.test(masked[index-1]);
      if (boundary && /^select\b/i.test(masked.slice(index))) { projecting = true; start=index+6; index+=5; continue; }
      if (projecting && boundary && /^(?:from|union|intersect|except)\b/i.test(masked.slice(index))) { finish(index); projecting=false; continue; }
      if (projecting && char === ",") { finish(index); start=index+1; }
    }
    if (projecting) finish(masked.length);
    return columns;
  }

  function validateGeneratedSql(sql) {
    const failures = [];
    if (typeof sql !== "string" || !sql.trim()) return [{code: "code.statements", message: "SQL content is required."}];
    const statements = splitSql(sql);
    if (!statements?.length) return [{code: "code.statements", message: "SQL has unclosed quotes/comments or no statements."}];
    const temporary = new Set();
    const noQuotes = sql.replace(/'(?:''|[^'])*'|`(?:``|[^`])*`|"(?:""|[^"])*"/g, "");
    if (/--|\/\*/.test(noQuotes)) failures.push({code: "code.statements", message: "SQL artifacts contain code only; keep explanatory comments in task or Mapping notes."});
    for (let index = 0; index < statements.length; index++) {
      const masked = maskSql(statements[index]).trim();
      const syntax = masked.replace(/`(?:``|[^`])*`|"(?:""|[^"])*"/g, "identifier");
      if (/\b(insert|update|delete|merge|drop|alter|truncate|copy|grant|revoke|call|execute|use|set|cache|uncache|vacuum|optimize|into)\b/i.test(syntax) || /\b(secret|try_secret|read_files)\s*\(/i.test(syntax)) {
        failures.push({code: "code.statements", message: "Transformation SQL cannot contain persistent writes, commands or credential/external-file functions."}); continue;
      }
      const last = index === statements.length - 1;
      if (last) {
        if (!/^select\b/i.test(masked)) { failures.push({code: "code.statements", message: "The final statement must be one explicit SELECT."}); continue; }
        const columns = finalProjection(masked);
        if (columns.some(column => !column || /^(?:(?:`[^`]+`|"[^"]+"|[A-Za-z_][\w$]*)\s*\.\s*)?\*(?:\s+(?:except|exclude|replace)\b.*)?$/i.test(column))) failures.push({code: "code.projection", message: "The final SELECT must list explicit target columns; wildcard projection is prohibited."});
        if (!physicalRelationsAreSafe(masked, temporary, 2)) failures.push({code: "code.stage-flow", message: "Read physical schema.table names or temporary views declared earlier in this file; runtime supplies the catalog."});
        continue;
      }
      const create = /^create\s+or\s+replace\s+temp(?:orary)?\s+view\s+(`[^`]+`|"[^"]+"|[A-Za-z_][\w$]*)\s+as\s+((?:select|with)\b[\s\S]+)$/i.exec(masked);
      if (!create) { failures.push({code: "code.statements", message: "Preparation uses CREATE OR REPLACE TEMPORARY VIEW with an unqualified name and query."}); continue; }
      const key = identifierKey(create[1]);
      if (temporary.has(key)) failures.push({code: "code.stage-flow", message: "Temporary stage names must be unique within the artifact."});
      if (!physicalRelationsAreSafe(create[2], temporary, 2)) failures.push({code: "code.stage-flow", message: "A stage reads an unresolved temporary relation or unsupported physical qualification."});
      temporary.add(key);
    }
    return failures;
  }

  function validateCodeRecords(loaded) {
    const value = loaded.get("generated_code");
    if (!value) return [];
    const originals = new Map(value.baseline.map(record => [core.stableStringify(core.key("model", value.definition, record)), record]));
    const issues = [];
    value.pending.forEach((record,index) => {
      const original = originals.get(core.stableStringify(core.key("model", value.definition, record)));
      if (record.artifact_type !== "sql_file" || core.active(record) !== true || core.stableStringify(original) === core.stableStringify(record)) return;
      for (const failure of validateGeneratedSql(record.generated_code_content)) issues.push({...failure, dataset:"generated_code", record:index+1,field:"generated_code_content"});
    });
    return issues;
  }
  return { splitSql, maskSql, identifierParts, physicalRelationsAreSafe, validateReadSql, validateGeneratedSql, validateCodeRecords };
});
