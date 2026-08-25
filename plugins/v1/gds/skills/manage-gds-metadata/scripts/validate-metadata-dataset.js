ObjC.import("Foundation");

function own(object, name) {
    return Object.prototype.hasOwnProperty.call(object, name);
}

function readText(path, label) {
    const data = $.NSData.dataWithContentsOfFile($(path));
    if (!data) {
        throw new Error(label + " cannot be read.");
    }
    const nativeText = $.NSString.alloc.initWithDataEncoding(
        data,
        $.NSUTF8StringEncoding
    );
    if (!nativeText) {
        throw new Error(label + " must be UTF-8.");
    }
    return ObjC.unwrap(nativeText);
}

function readJson(path, label) {
    try {
        return JSON.parse(readText(path, label));
    } catch (_error) {
        throw new Error(label + " is not valid JSON.");
    }
}

function isObject(value) {
    return value !== null && !Array.isArray(value) && typeof value === "object";
}

function sameScalar(left, right) {
    return typeof left === typeof right && left === right;
}

function validDate(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (!match) {
        return false;
    }
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const date = new Date(Date.UTC(year, month - 1, day));
    return date.getUTCFullYear() === year &&
        date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

function validDateTime(value) {
    return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
        !isNaN(Date.parse(value));
}

function matchesType(value, expected) {
    if (expected === "null") {
        return value === null;
    }
    if (expected === "string") {
        return typeof value === "string";
    }
    if (expected === "boolean") {
        return typeof value === "boolean";
    }
    if (expected === "integer") {
        return typeof value === "number" && isFinite(value) && Math.floor(value) === value;
    }
    if (expected === "number") {
        return typeof value === "number" && isFinite(value);
    }
    if (expected === "object") {
        return isObject(value);
    }
    return false;
}

function matchesValueSchema(value, rule) {
    if (!isObject(rule)) {
        return false;
    }
    if (Array.isArray(rule.anyOf)) {
        for (let index = 0; index < rule.anyOf.length; index += 1) {
            if (matchesValueSchema(value, rule.anyOf[index])) {
                return true;
            }
        }
        return false;
    }
    if (typeof rule.type !== "string" || !matchesType(value, rule.type)) {
        return false;
    }
    if (typeof value === "string") {
        if (typeof rule.minLength === "number" && value.length < rule.minLength) {
            return false;
        }
        if (typeof rule.maxLength === "number" && value.length > rule.maxLength) {
            return false;
        }
        if (typeof rule.pattern === "string" && !new RegExp(rule.pattern).test(value)) {
            return false;
        }
        if (rule.format === "date" && !validDate(value)) {
            return false;
        }
        if (rule.format === "date-time" && !validDateTime(value)) {
            return false;
        }
    }
    if (typeof value === "number") {
        if (typeof rule.minimum === "number" && value < rule.minimum) {
            return false;
        }
        if (typeof rule.maximum === "number" && value > rule.maximum) {
            return false;
        }
        if (typeof rule.exclusiveMinimum === "number" && value <= rule.exclusiveMinimum) {
            return false;
        }
        if (typeof rule.exclusiveMaximum === "number" && value >= rule.exclusiveMaximum) {
            return false;
        }
    }
    if (Array.isArray(rule.enum)) {
        let found = false;
        for (let index = 0; index < rule.enum.length; index += 1) {
            if (sameScalar(value, rule.enum[index])) {
                found = true;
                break;
            }
        }
        if (!found) {
            return false;
        }
    }
    if (own(rule, "const") && !sameScalar(value, rule.const)) {
        return false;
    }
    return true;
}

function validateSchema(schema, expectedDataset) {
    const normalization = schema && schema["x-gds-key-normalization"];
    if (!isObject(schema) || schema.type !== "object" ||
        schema.additionalProperties !== false || !isObject(schema.properties) ||
        !Array.isArray(schema.required) ||
        schema["x-gds-dataset"] !== expectedDataset ||
        schema["x-gds-change-set-eligible"] !== true ||
        !Array.isArray(schema["x-gds-canonical-key"]) ||
        !Array.isArray(schema["x-gds-unique-constraints"]) ||
        !isObject(normalization) || normalization.version !== "1.0" ||
        !Array.isArray(normalization.string_field_suffixes) ||
        normalization.string_field_suffixes.join("\u001f") !== "_code\u001f_name\u001f_schema" ||
        !Array.isArray(normalization.trim_code_points) ||
        normalization.trim_code_points.join("\u001f") !== "U+0020" ||
        normalization.case !== "unicode-lowercase" ||
        normalization.unicode_normalization !== "none" ||
        normalization.other_values !== "identity") {
        throw new Error("Snapshot dataset schema contract is invalid.");
    }
}

function validateRecord(record, schema) {
    if (!isObject(record)) {
        throw new Error("Every dataset item must be a JSON object.");
    }
    const fields = Object.keys(record);
    for (let index = 0; index < fields.length; index += 1) {
        const field = fields[index];
        const normalized = field.toLowerCase();
        if (normalized === "id" || normalized.endsWith("_id")) {
            throw new Error("Database ID fields are forbidden.");
        }
        if (!own(schema.properties, field)) {
            throw new Error("Record contains an unknown schema field: " + field + ".");
        }
        if (!matchesValueSchema(record[field], schema.properties[field])) {
            throw new Error("Record field does not match the schema: " + field + ".");
        }
    }
    for (let index = 0; index < schema.required.length; index += 1) {
        const field = schema.required[index];
        if (!own(record, field)) {
            throw new Error("Record is missing a required schema field: " + field + ".");
        }
    }
}

function normalizedKey(record, columns, schema) {
    const normalization = schema["x-gds-key-normalization"];
    const values = [];
    for (let index = 0; index < columns.length; index += 1) {
        const field = columns[index];
        if (!own(record, field)) {
            throw new Error("Record is missing a key field: " + field + ".");
        }
        const value = record[field];
        if (value === null) {
            values.push(["null", null]);
        } else if (typeof value === "string") {
            const normalizeString = normalization.string_field_suffixes.some(
                function (suffix) { return field.endsWith(suffix); }
            );
            values.push([
                "string",
                normalizeString ? value.replace(/^ +| +$/g, "").toLowerCase() : value
            ]);
        } else if (typeof value === "number" || typeof value === "boolean") {
            values.push([typeof value, value]);
        } else {
            throw new Error("Key field must be a scalar: " + field + ".");
        }
    }
    return JSON.stringify(values);
}

function validateDataset(records, schema) {
    if (!Array.isArray(records)) {
        throw new Error("Dataset file must contain one JSON array.");
    }
    if (records.length > 50000) {
        throw new Error("Dataset file exceeds 50000 records.");
    }
    for (let index = 0; index < records.length; index += 1) {
        validateRecord(records[index], schema);
    }
    const constraints = schema["x-gds-unique-constraints"];
    for (let constraintIndex = 0; constraintIndex < constraints.length; constraintIndex += 1) {
        const columns = constraints[constraintIndex];
        if (!Array.isArray(columns) || columns.length === 0) {
            throw new Error("Snapshot unique constraint is invalid.");
        }
        const seen = {};
        for (let recordIndex = 0; recordIndex < records.length; recordIndex += 1) {
            const key = normalizedKey(records[recordIndex], columns, schema);
            if (own(seen, key)) {
                throw new Error("Dataset contains a duplicate unique constraint.");
            }
            seen[key] = true;
        }
    }
}

function validateCanonicalKey(keyRecord, schema) {
    if (!isObject(keyRecord)) {
        throw new Error("Canonical key input must be one JSON object.");
    }
    const columns = schema["x-gds-canonical-key"];
    const fields = Object.keys(keyRecord);
    if (fields.length !== columns.length) {
        throw new Error("Canonical key input must contain exactly its schema fields.");
    }
    for (let index = 0; index < columns.length; index += 1) {
        const field = columns[index];
        if (!own(keyRecord, field) ||
            !matchesValueSchema(keyRecord[field], schema.properties[field])) {
            throw new Error("Canonical key input does not match its schema.");
        }
    }
    for (let index = 0; index < fields.length; index += 1) {
        if (columns.indexOf(fields[index]) === -1) {
            throw new Error("Canonical key input contains an unknown field.");
        }
    }
}

function readJsonLines(path) {
    const text = readText(path, "Snapshot rows");
    const records = [];
    const lines = text.split(/\r?\n/);
    for (let index = 0; index < lines.length; index += 1) {
        if (!lines[index].trim()) {
            continue;
        }
        let record;
        try {
            record = JSON.parse(lines[index]);
        } catch (_error) {
            throw new Error("Snapshot rows contain invalid JSON.");
        }
        if (!isObject(record)) {
            throw new Error("Snapshot row must be a JSON object.");
        }
        records.push(record);
    }
    return records;
}

function matchingRecord(records, keyRecord, schema, label) {
    const columns = schema["x-gds-canonical-key"];
    const wanted = normalizedKey(keyRecord, columns, schema);
    let found = null;
    for (let index = 0; index < records.length; index += 1) {
        if (normalizedKey(records[index], columns, schema) !== wanted) {
            continue;
        }
        if (found !== null) {
            throw new Error(label + " contains duplicate canonical keys.");
        }
        found = records[index];
    }
    return found;
}

function validateChanges(changes, schema) {
    if (!isObject(changes) || Object.keys(changes).length === 0) {
        throw new Error("Field changes must be one nonempty JSON object.");
    }
    const canonical = schema["x-gds-canonical-key"];
    Object.keys(changes).forEach(function (field) {
        const normalized = field.toLowerCase();
        if (normalized === "id" || normalized.endsWith("_id")) {
            throw new Error("Database ID fields are forbidden.");
        }
        if (canonical.indexOf(field) !== -1) {
            throw new Error("Field changes cannot modify the canonical key.");
        }
        if (!own(schema.properties, field)) {
            throw new Error("Field changes contain an unknown schema field.");
        }
        if (!matchesValueSchema(changes[field], schema.properties[field])) {
            throw new Error("Changed field does not match the schema.");
        }
    });
}

function recordsEqual(left, right, schema) {
    return Object.keys(schema.properties).every(function (field) {
        return JSON.stringify(left[field]) === JSON.stringify(right[field]);
    });
}

function writeDataset(path, records) {
    const text = JSON.stringify(records, null, 2) + "\n";
    const data = $(text).dataUsingEncoding($.NSUTF8StringEncoding);
    if (!data || Number(data.length) > 16777216) {
        throw new Error("Result exceeds the 16 MiB Stage limit.");
    }
    if (!data.writeToFileAtomically($(path), true)) {
        throw new Error("Dataset file could not be written atomically.");
    }
}

function run(arguments) {
    if (arguments.length !== 3 && arguments.length !== 5 &&
        !(arguments.length === 6 && arguments[5] === "remove") &&
        !(arguments.length === 8 && arguments[7] === "edit")) {
        throw new Error("Invalid dataset helper arguments.");
    }
    const schema = readJson(arguments[0], "Snapshot dataset schema");
    const datasetPath = arguments[1];
    const datasetName = arguments[2];
    validateSchema(schema, datasetName);

    if (arguments.length === 3) {
        const records = readJson(datasetPath, "Dataset JSON");
        validateDataset(records, schema);
        return "record_count=" + records.length;
    }

    let records = [];
    if ($.NSFileManager.defaultManager.fileExistsAtPath($(datasetPath))) {
        records = readJson(datasetPath, "Dataset JSON");
        validateDataset(records, schema);
    }

    if (arguments.length === 8) {
        const keyRecord = readJson(arguments[3], "Canonical key JSON");
        const changes = readJson(arguments[4], "Field changes JSON");
        validateCanonicalKey(keyRecord, schema);
        validateChanges(changes, schema);
        const snapshotRecords = readJsonLines(arguments[5]);
        validateDataset(snapshotRecords, schema);
        const snapshotRecord = matchingRecord(snapshotRecords, keyRecord, schema, "Snapshot");
        if (snapshotRecord === null) {
            throw new Error("Snapshot has no record matching the canonical key.");
        }
        const pendingRecord = matchingRecord(records, keyRecord, schema, "Local dataset");
        const base = pendingRecord === null ? snapshotRecord : pendingRecord;
        const proposed = JSON.parse(JSON.stringify(base));
        Object.keys(changes).forEach(function (field) {
            proposed[field] = changes[field];
        });
        validateRecord(proposed, schema);
        if (recordsEqual(proposed, base, schema)) {
            return "mode=field-edit\nbase=" + (pendingRecord === null ? "snapshot" : "pending") +
                "\naction=no_change\nchanged_field_count=" + Object.keys(changes).length +
                "\nrecord_count=" + records.length + "\nreview_stale=false";
        }
        const canonicalKey = schema["x-gds-canonical-key"];
        const wanted = normalizedKey(proposed, canonicalKey, schema);
        let matchedIndex = -1;
        for (let index = 0; index < records.length; index += 1) {
            if (normalizedKey(records[index], canonicalKey, schema) === wanted) {
                matchedIndex = index;
                break;
            }
        }
        const action = matchedIndex === -1 ? "inserted" : "replaced";
        if (matchedIndex === -1) {
            records.push(proposed);
        } else {
            records[matchedIndex] = proposed;
        }
        validateDataset(records, schema);
        writeDataset(arguments[6], records);
        return "mode=field-edit\nbase=" + (pendingRecord === null ? "snapshot" : "pending") +
            "\naction=" + action + "\nchanged_field_count=" + Object.keys(changes).length +
            "\nrecord_count=" + records.length + "\nreview_stale=true";
    }

    if (arguments.length === 6) {
        const keyRecord = readJson(arguments[3], "Canonical key JSON");
        validateCanonicalKey(keyRecord, schema);
        const wantedKey = normalizedKey(
            keyRecord,
            schema["x-gds-canonical-key"],
            schema
        );
        let matchedIndex = -1;
        for (let index = 0; index < records.length; index += 1) {
            if (normalizedKey(records[index], schema["x-gds-canonical-key"], schema) === wantedKey) {
                matchedIndex = index;
                break;
            }
        }
        if (matchedIndex === -1) {
            return "action=not_found\nrecord_count=" + records.length;
        }
        records.splice(matchedIndex, 1);
        validateDataset(records, schema);
        writeDataset(arguments[4], records);
        return "action=removed\nrecord_count=" + records.length;
    }

    const record = readJson(arguments[3], "Input record JSON");
    validateRecord(record, schema);
    const canonicalKey = schema["x-gds-canonical-key"];
    const wanted = normalizedKey(record, canonicalKey, schema);
    let matchedIndex = -1;
    for (let index = 0; index < records.length; index += 1) {
        if (normalizedKey(records[index], canonicalKey, schema) === wanted) {
            if (matchedIndex !== -1) {
                throw new Error("Dataset contains duplicate canonical keys.");
            }
            matchedIndex = index;
        }
    }
    let action = "inserted";
    if (matchedIndex === -1) {
        records.push(record);
    } else {
        records[matchedIndex] = record;
        action = "replaced";
    }
    validateDataset(records, schema);
    writeDataset(arguments[4], records);
    return "mode=full-record\naction=" + action + "\nrecord_count=" + records.length +
        "\nreview_stale=true";
}
