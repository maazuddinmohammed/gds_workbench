ObjC.import("Foundation");

function own(object, name) {
    return Object.prototype.hasOwnProperty.call(object, name);
}

function isObject(value) {
    return value !== null && !Array.isArray(value) && typeof value === "object";
}

function readText(path, label) {
    const data = $.NSData.dataWithContentsOfFile($(path));
    const text = $.NSString.alloc.initWithDataEncoding(
        data,
        $.NSUTF8StringEncoding
    );
    if (!text) {
        throw new Error(label + " cannot be read as UTF-8.");
    }
    return ObjC.unwrap(text);
}

function readJson(path, label) {
    try {
        return JSON.parse(readText(path, label));
    } catch (_error) {
        throw new Error(label + " is not valid JSON.");
    }
}

function normalizationContract(schema) {
    const normalization = schema && schema["x-gds-key-normalization"];
    if (!isObject(normalization) || normalization.version !== "1.0" ||
        !Array.isArray(normalization.string_field_suffixes) ||
        normalization.string_field_suffixes.join("\u001f") !== "_code\u001f_name\u001f_schema" ||
        !Array.isArray(normalization.trim_code_points) ||
        normalization.trim_code_points.join("\u001f") !== "U+0020" ||
        normalization.case !== "unicode-lowercase" ||
        normalization.unicode_normalization !== "none" ||
        normalization.other_values !== "identity") {
        throw new Error("Snapshot key-normalization contract is invalid.");
    }
    return normalization;
}

function normalizedKey(record, columns, schema) {
    const normalization = normalizationContract(schema);
    const values = [];
    for (let index = 0; index < columns.length; index += 1) {
        const field = columns[index];
        if (!own(record, field)) {
            throw new Error("Record is missing a canonical-key field.");
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
            throw new Error("Canonical-key field is not a scalar.");
        }
    }
    return JSON.stringify(values);
}

function recordsEqual(left, right, fields) {
    for (let index = 0; index < fields.length; index += 1) {
        const field = fields[index];
        if (!own(left, field) || !own(right, field) ||
            typeof left[field] !== typeof right[field] || left[field] !== right[field]) {
            return false;
        }
    }
    return true;
}

function keyObject(record, columns) {
    const result = {};
    for (let index = 0; index < columns.length; index += 1) {
        result[columns[index]] = record[columns[index]];
    }
    return result;
}

function snapshotMatches(path, wanted) {
    const result = {};
    const lines = readText(path, "Snapshot rows").split(/\r?\n/);
    for (let index = 0; index < lines.length; index += 1) {
        if (lines[index].trim() === "") {
            continue;
        }
        let row;
        try {
            row = JSON.parse(lines[index]);
        } catch (_error) {
            throw new Error("Snapshot rows contain invalid JSON.");
        }
        const key = normalizedKey(row, wanted.columns, wanted.schema);
        if (own(wanted.keys, key)) {
            if (own(result, key)) {
                throw new Error("Snapshot contains a duplicate canonical key.");
            }
            result[key] = row;
        }
    }
    return result;
}

function writeJson(path, value) {
    const text = JSON.stringify(value, null, 2) + "\n";
    const data = $(text).dataUsingEncoding($.NSUTF8StringEncoding);
    if (!data || Number(data.length) > 33554432) {
        throw new Error("Stage review exceeds 32 MiB.");
    }
    if (!data.writeToFileAtomically($(path), true)) {
        throw new Error("Stage review could not be written atomically.");
    }
}

function run(arguments) {
    if (arguments.length < 5 || (arguments.length - 3) % 2 !== 0) {
        throw new Error("Invalid stage-review arguments.");
    }
    const changeSetPath = arguments[0];
    const snapshotPath = arguments[1];
    const outputPath = arguments[2];
    const state = readJson(changeSetPath + "/change-set.json", "Local Change Set state");
    const datasets = {};
    const totals = {
        insert: 0,
        update: 0,
        deactivate: 0,
        reactivate: 0,
        no_change: 0
    };
    let recordTotal = 0;
    let datasetTotal = 0;
    let summary = "";

    for (let argumentIndex = 3; argumentIndex < arguments.length; argumentIndex += 2) {
        const name = arguments[argumentIndex];
        const sha256 = arguments[argumentIndex + 1];
        if (!/^[0-9a-f]{64}$/.test(sha256) || own(datasets, name)) {
            throw new Error("Stage-review dataset arguments are invalid.");
        }
        const schema = readJson(
            snapshotPath + "/schemas/" + name + ".schema.json",
            "Snapshot dataset schema"
        );
        const records = readJson(
            changeSetPath + "/datasets/" + name + ".json",
            "Local dataset"
        );
        const columns = schema["x-gds-canonical-key"];
        const fields = Object.keys(schema.properties);
        if (!Array.isArray(records) || !Array.isArray(columns)) {
            throw new Error("Stage-review dataset contract is invalid.");
        }
        normalizationContract(schema);
        const wanted = {columns: columns, keys: {}, schema: schema};
        for (let recordIndex = 0; recordIndex < records.length; recordIndex += 1) {
            wanted.keys[normalizedKey(records[recordIndex], columns, schema)] = true;
        }
        const baseline = snapshotMatches(
            snapshotPath + "/data/operational/" + name + "/rows.jsonl",
            wanted
        );
        const actionCounts = {
            insert: 0,
            update: 0,
            deactivate: 0,
            reactivate: 0,
            no_change: 0
        };
        const reviewedRecords = [];
        for (let recordIndex = 0; recordIndex < records.length; recordIndex += 1) {
            const record = records[recordIndex];
            const normalized = normalizedKey(record, columns, schema);
            const existing = baseline[normalized];
            let action = "insert";
            if (existing) {
                if (recordsEqual(record, existing, fields)) {
                    action = "no_change";
                } else if (own(record, "is_active") && own(existing, "is_active") &&
                    existing.is_active === true && record.is_active === false) {
                    action = "deactivate";
                } else if (own(record, "is_active") && own(existing, "is_active") &&
                    existing.is_active === false && record.is_active === true) {
                    action = "reactivate";
                } else {
                    action = "update";
                }
            }
            actionCounts[action] += 1;
            totals[action] += 1;
            const reviewed = {
                action: action,
                canonical_key: keyObject(record, columns)
            };
            if (own(record, "is_active")) {
                reviewed.is_active = record.is_active;
            }
            reviewedRecords.push({sort_key: normalized, value: reviewed});
        }
        reviewedRecords.sort(function (left, right) {
            return left.sort_key < right.sort_key ? -1 : left.sort_key > right.sort_key ? 1 : 0;
        });
        datasets[name] = {
            file: "datasets/" + name + ".json",
            sha256: sha256,
            record_count: records.length,
            canonical_key: columns,
            actions: actionCounts,
            records: reviewedRecords.map(function (item) { return item.value; })
        };
        summary += "dataset=" + name + "|" + records.length + "|" +
            actionCounts.insert + "|" + actionCounts.update + "|" +
            actionCounts.deactivate + "|" + actionCounts.reactivate + "|" +
            actionCounts.no_change + "|" + sha256 + "\n";
        recordTotal += records.length;
        datasetTotal += 1;
    }

    const review = {
        format_version: "1.0",
        tenant: {
            tenant_id: state.tenant.tenant_id,
            tenant_code: state.tenant.tenant_code
        },
        snapshot_id: state.snapshot.snapshot_id,
        server_change_set: {
            metadata_change_set_id: state.server_change_set.metadata_change_set_id,
            draft_revision: state.server_change_set.draft_revision
        },
        datasets: datasets
    };
    writeJson(outputPath, review);
    summary += "dataset_count=" + datasetTotal + "\n";
    summary += "record_count=" + recordTotal + "\n";
    summary += "insert_count=" + totals.insert + "\n";
    summary += "update_count=" + totals.update + "\n";
    summary += "deactivate_count=" + totals.deactivate + "\n";
    summary += "reactivate_count=" + totals.reactivate + "\n";
    summary += "no_change_count=" + totals.no_change;
    return summary;
}
