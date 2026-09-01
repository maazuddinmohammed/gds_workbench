-- Illustrative GDS/Julius layout for one target Object with two source Systems.
-- Replace names and expressions only from Mapping/Process/user evidence.

CREATE OR REPLACE TEMPORARY VIEW temp_system_a_target AS
SELECT
  operating.OperatingEntityID,
  trim(source.NaturalKey) AS TargetNaturalKey,
  coalesce(trim(prior.BusinessName), trim(source.Description)) AS BusinessName,
  source_system.SourceSystemID
FROM catalog_name.bronze.system_a_source AS source
LEFT JOIN catalog_name.meta.source_system AS source_system
  ON lower(trim(source_system.SourceSystemCode)) = 'system_a'
LEFT JOIN catalog_name.common.operating_entity AS operating
  ON lower(trim(operating.OperatingEntityName)) = 'system_a_entity'
LEFT JOIN catalog_name.silver.target_object AS prior
  ON trim(source.NaturalKey) = trim(prior.TargetNaturalKey)
 AND trim(operating.OperatingEntityID) = trim(prior.OperatingEntityID)
WHERE source.gds_batch_id = wid_GDSBatchID;

CREATE OR REPLACE TEMPORARY VIEW temp_system_b_target AS
SELECT
  operating.OperatingEntityID,
  trim(source.ReferenceCode) AS TargetNaturalKey,
  coalesce(trim(prior.BusinessName), trim(source.ReferenceName)) AS BusinessName,
  source_system.SourceSystemID
FROM catalog_name.bronze.system_b_source AS source
LEFT JOIN catalog_name.meta.source_system AS source_system
  ON lower(trim(source_system.SourceSystemCode)) = 'system_b'
LEFT JOIN catalog_name.common.operating_entity AS operating
  ON lower(trim(operating.OperatingEntityName)) = 'system_b_entity'
LEFT JOIN catalog_name.silver.target_object AS prior
  ON trim(source.ReferenceCode) = trim(prior.TargetNaturalKey)
 AND trim(operating.OperatingEntityID) = trim(prior.OperatingEntityID)
WHERE source.gds_batch_id = wid_GDSBatchID;

-- Final statement only: exact target shape. The runtime performs the natural-key merge.
SELECT * FROM temp_system_a_target
UNION ALL
SELECT * FROM temp_system_b_target;
