-- PROPOSAL (draft, not installed). Additions to database/01_reference.sql.
--
-- Two kinds of value lists:
--
--   Labels: no code does anything different per value; the value only informs the AI
--   and people. These live in reference tables, like reference.context_type today.
--   Adding a value is one INSERT, with no DDL, code or prompt change. The backend reads
--   the active rows to validate AI output, list the allowed values (with descriptions)
--   in the prompt, and fill the screen dropdowns.
--
--   Behavior switches: the backend does something different per value, so a new value
--   needs new code anyway, and the DDL change ships with it. These stay fixed CHECK
--   lists:
--     dimensional_entity_type    fact | dimension | bridge (key and audit columns differ)
--     relationship cardinality   many_to_one | one_to_one
--     Validate check_code / check_result
--
-- Lists are global, like Context Types. Retire a value with is_active = FALSE: old rows
-- keep it, new AI output can't use it.

CREATE TABLE reference.logical_entity_type (
    logical_entity_type_code         VARCHAR(50) PRIMARY KEY,         -- what the AI writes, e.g. 'transaction'
    logical_entity_type_description  TEXT NOT NULL,                   -- shown to the AI and in the UI
    logical_entity_type_is_active    BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO reference.logical_entity_type (logical_entity_type_code, logical_entity_type_description) VALUES
    ('core',        'A main business thing with its own identity, such as Customer or Product.'),
    ('reference',   'A short list of codes and their meanings, such as Country or OrderStatus.'),
    ('transaction', 'A business document or exchange, such as SalesOrder or Invoice, often with lines.'),
    ('event',       'Something that happened at a point in time, such as a login or a shipment scan.'),
    ('association', 'Links entities many-to-many, such as ProductCategory.'),
    ('history',     'Past versions of another entity''s values over time.'),
    ('snapshot',    'The state of something at regular points in time, such as month-end balances.');

CREATE TABLE reference.dimensional_fact_type (
    dimensional_fact_type_code         VARCHAR(50) PRIMARY KEY,       -- e.g. 'periodic_snapshot'
    dimensional_fact_type_description  TEXT NOT NULL,                 -- shown to the AI and in the UI
    dimensional_fact_type_is_active    BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO reference.dimensional_fact_type (dimensional_fact_type_code, dimensional_fact_type_description) VALUES
    ('transaction',           'One row per business event at its lowest detail.'),
    ('periodic_snapshot',     'One row per thing per period, such as daily stock levels.'),
    ('accumulating_snapshot', 'One row per process instance, updated as it moves through its steps, such as order fulfilment.'),
    ('factless',              'Records that something happened or applies, with no measures, such as attendance.');

-- Adding a value later, for example:
--   INSERT INTO reference.logical_entity_type VALUES
--       ('staging', 'A working copy kept only to assemble another entity.', TRUE);
