-- Replace quoted identifiers only, from registered eligible metadata.
-- Do not execute for a masked Attribute or a masked resolved Source Attribute.
-- Values stay inside this read; only type/count leave the SQL engine.
-- Provisional syntax evidence only: never infer target capacity from sample width.
WITH sample AS (
    SELECT CAST(`__attribute__` AS STRING) AS value
    FROM `__catalog__`.`__schema__`.`__table__`
    WHERE `__attribute__` IS NOT NULL
    LIMIT 50
), normalized AS (
    SELECT regexp_replace(value,
               r'^[\p{javaWhitespace}\u0085\u00a0\u2007\u202f]+|[\p{javaWhitespace}\u0085\u00a0\u2007\u202f]+$',
               '') AS value,
           length(value) <= 20000 AS bounded
    FROM sample
), observed AS (
    SELECT value, bounded FROM normalized WHERE value <> ''
), classified AS (
    SELECT value, bounded,
           lower(value) IN ('true', 'false') AS is_boolean,
           value RLIKE '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
               AND try_cast(value AS DATE) IS NOT NULL AS is_date,
           value RLIKE '^[0-9]{4}-[0-9]{2}-[0-9]{2}[T ]([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]([.][0-9]{1,6})?$'
               AND try_cast(value AS TIMESTAMP_NTZ) IS NOT NULL AS is_naive_timestamp,
           value RLIKE '^[0-9]{4}-[0-9]{2}-[0-9]{2}[T ]([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]([.][0-9]{1,6})?(Z|[+-]([01][0-9]|2[0-3]):[0-5][0-9])$'
               AND try_cast(value AS TIMESTAMP) IS NOT NULL AS is_zoned_timestamp,
           value RLIKE '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$' AS is_numeric,
           value RLIKE '^[+-]?[0-9]+$'
               AND try_cast(value AS BIGINT) IS NOT NULL AS is_bigint,
           value RLIKE '^[+-]?0[0-9]' AS has_leading_zero,
           regexp_extract(value, '^[+-]?([^eE]+)', 1) AS mantissa,
           CASE WHEN value RLIKE '[eE]'
               THEN try_cast(regexp_extract(value, '[eE]([+-]?[0-9]+)$', 1) AS BIGINT)
               ELSE 0 END AS exponent
    FROM observed
), exact_digits AS (
    SELECT *,
           greatest(1, length(regexp_replace(
               regexp_replace(mantissa, '[.]', ''), '^0+', ''
           ))) AS significant_digits,
           CASE WHEN instr(mantissa, '.') > 0
               THEN length(mantissa) - instr(mantissa, '.') ELSE 0 END AS fractional_digits
    FROM classified
), totals AS (
    SELECT count(*) AS sample_count,
           coalesce(bool_and(bounded), TRUE) AS bounded,
           coalesce(bool_and(is_boolean), FALSE) AS all_boolean,
           coalesce(bool_and(is_date), FALSE) AS all_date,
           coalesce(bool_and(is_date OR is_naive_timestamp), FALSE) AS all_date_or_naive,
           coalesce(bool_and(is_zoned_timestamp), FALSE) AS all_zoned,
           -- Up to 20,000 fractional digits can offset a positive exponent.
           coalesce(bool_and(is_numeric AND NOT has_leading_zero
               AND exponent IS NOT NULL AND exponent BETWEEN -38 AND 20038), FALSE) AS exact_numeric,
           coalesce(bool_and(is_bigint), FALSE) AS all_bigint,
           max(greatest(significant_digits
               + CASE WHEN exponent BETWEEN -38 AND 20038 THEN exponent ELSE 0 END
               - fractional_digits, 0)) AS integer_digits,
           max(greatest(fractional_digits
               - CASE WHEN exponent BETWEEN -38 AND 20038 THEN exponent ELSE 0 END, 0)) AS scale
    FROM exact_digits
)
SELECT CASE
           WHEN sample_count = 0 OR NOT bounded THEN NULL
           WHEN all_boolean THEN 'BOOLEAN'
           WHEN all_date THEN 'DATE'
           WHEN all_date_or_naive THEN 'TIMESTAMP_NTZ'
           WHEN all_zoned THEN 'TIMESTAMP'
           WHEN exact_numeric AND integer_digits + scale <= 38 THEN
               CASE WHEN all_bigint THEN 'BIGINT'
                   ELSE concat('DECIMAL(38,', scale, ')') END
           ELSE 'STRING'
       END AS inferred_data_type,
       sample_count
FROM totals;
