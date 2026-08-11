-- Test-only Metadata Snapshot seed. Execute exactly once in a new test database.
-- Run with psql --single-transaction and ON_ERROR_STOP=1.

INSERT INTO reference.system_type (
    system_type_code,
    system_type_name,
    system_type_description
)
VALUES ('DEMO_DATABASE', 'Demo Database', 'Test-only database system type');

INSERT INTO reference.connection_type (
    connection_type_code,
    connection_type_name,
    connection_type_description
)
VALUES ('DEMO_POSTGRESQL', 'Demo PostgreSQL', 'Test-only PostgreSQL connection');

INSERT INTO reference.object_type (
    object_type_code,
    object_type_name,
    object_type_description
)
VALUES ('TABLE', 'Table', 'Relational table');

INSERT INTO reference.zone (zone_code, zone_name, zone_description)
VALUES
    ('source', 'Source', 'Source-system metadata'),
    ('bronze', 'Bronze', 'Raw global-data-store metadata'),
    ('silver', 'Silver', 'Conformed global-data-store metadata'),
    ('gold', 'Gold', 'Presentation global-data-store metadata');

INSERT INTO reference.chunk_type (
    chunk_type_name,
    chunk_type_description
)
VALUES ('Full', 'Test-only full-load chunk');

INSERT INTO reference.file_type (
    file_type_name,
    file_type_description
)
VALUES ('Parquet', 'Apache Parquet file');

INSERT INTO reference.data_operation (
    data_operation_name,
    data_operation_description
)
VALUES
    ('Read', 'Read source records'),
    ('Write', 'Write target records');

INSERT INTO reference.process_type (
    process_type_name,
    process_type_description
)
VALUES ('Notebook', 'Notebook-backed metadata process');

INSERT INTO core.project (
    project_code,
    project_name,
    project_description
)
VALUES ('DEMO_PROJECT', 'Metadata Snapshot Demo', 'Test-only snapshot project');

INSERT INTO core.tenant (
    project_id,
    tenant_code,
    tenant_name,
    tenant_description,
    tenant_catalog,
    gds_admin_catalog,
    tenant_visibility
)
SELECT project_id,
       'DEMO_TENANT',
       'Metadata Snapshot Demo Tenant',
       'Private Tenant used for Metadata Snapshot testing',
       'demo_tenant_catalog',
       'demo_tenant_admin',
       'private'
  FROM core.project
 WHERE project_code = 'DEMO_PROJECT';

INSERT INTO core.tenant (
    project_id,
    tenant_code,
    tenant_name,
    tenant_description,
    tenant_catalog,
    gds_admin_catalog,
    tenant_visibility
)
SELECT project_id,
       'DEMO_GDS_TENANT',
       'Metadata Snapshot Demo Global Store',
       'Global-data-store Tenant used for Metadata Snapshot testing',
       'demo_gds_catalog',
       'demo_gds_admin',
       'private'
  FROM core.project
 WHERE project_code = 'DEMO_PROJECT';

INSERT INTO core.system (
    system_code,
    system_name,
    system_description,
    system_type_id
)
SELECT 'DEMO_CUSTOMER_SYSTEM',
       'Demo Customer System',
       'Test-only customer source and processing system',
       system_type_id
  FROM reference.system_type
 WHERE system_type_code = 'DEMO_DATABASE';

INSERT INTO core.connection (
    tenant_id,
    system_id,
    connection_code,
    connection_name,
    connection_type_id,
    is_global_data_store
)
SELECT tenant.tenant_id,
       system.system_id,
       'DEMO_SOURCE',
       'Demo Customer Source',
       connection_type.connection_type_id,
       FALSE
  FROM core.tenant AS tenant
 CROSS JOIN core.system AS system
 CROSS JOIN reference.connection_type AS connection_type
 WHERE tenant.tenant_code = 'DEMO_TENANT'
   AND system.system_code = 'DEMO_CUSTOMER_SYSTEM'
   AND connection_type.connection_type_code = 'DEMO_POSTGRESQL';

INSERT INTO core.connection (
    tenant_id,
    system_id,
    connection_code,
    connection_name,
    connection_type_id,
    is_global_data_store
)
SELECT tenant.tenant_id,
       system.system_id,
       'DEMO_GDS',
       'Demo Global Data Store',
       connection_type.connection_type_id,
       TRUE
  FROM core.tenant AS tenant
 CROSS JOIN core.system AS system
 CROSS JOIN reference.connection_type AS connection_type
 WHERE tenant.tenant_code = 'DEMO_GDS_TENANT'
   AND system.system_code = 'DEMO_CUSTOMER_SYSTEM'
   AND connection_type.connection_type_code = 'DEMO_POSTGRESQL';

UPDATE core.tenant AS tenant
   SET gds_connection_id = connection.connection_id
  FROM core.connection AS connection
 WHERE tenant.tenant_code = 'DEMO_TENANT'
   AND connection.connection_code = 'DEMO_GDS';

INSERT INTO core.tenant_metadata_discovery_scope (
    tenant_id,
    connection_id,
    zone_id,
    object_schema
)
SELECT tenant.tenant_id,
       connection.connection_id,
       zone.zone_id,
       zone_schema.object_schema
  FROM core.tenant AS tenant
 CROSS JOIN core.connection AS connection
 JOIN (
        VALUES
            ('bronze', 'bronze_demo'),
            ('silver', 'silver_demo'),
            ('gold', 'gold_demo')
       ) AS zone_schema(zone_code, object_schema)
    ON TRUE
 JOIN reference.zone AS zone
   ON zone.zone_code = zone_schema.zone_code
 WHERE tenant.tenant_code = 'DEMO_TENANT'
   AND connection.connection_code = 'DEMO_GDS';

INSERT INTO core.object (
    connection_id,
    object_schema,
    object_name,
    object_description,
    object_type_id,
    zone_id
)
SELECT connection.connection_id,
       object_seed.object_schema,
       object_seed.object_name,
       object_seed.object_description,
       object_type.object_type_id,
       zone.zone_id
  FROM (
        VALUES
            (
                'DEMO_SOURCE',
                'source',
                'source_demo',
                'customer',
                'Source customer records'
            ),
            (
                'DEMO_GDS',
                'bronze',
                'bronze_demo',
                'customer',
                'Raw customer records'
            ),
            (
                'DEMO_GDS',
                'silver',
                'silver_demo',
                'customer',
                'Conformed customer records'
            ),
            (
                'DEMO_GDS',
                'gold',
                'gold_demo',
                'dim_customer',
                'Customer dimension'
            )
       ) AS object_seed(
           connection_code,
           zone_code,
           object_schema,
           object_name,
           object_description
       )
 JOIN core.connection AS connection
   ON connection.connection_code = object_seed.connection_code
 JOIN reference.zone AS zone
   ON zone.zone_code = object_seed.zone_code
 CROSS JOIN reference.object_type AS object_type
 WHERE object_type.object_type_code = 'TABLE';

INSERT INTO core.attribute (
    object_id,
    attribute_name,
    attribute_ordinal_position,
    attribute_description,
    attribute_data_type,
    attribute_nullability,
    is_natural_key,
    is_mapped
)
SELECT object.object_id,
       attribute_seed.attribute_name,
       attribute_seed.attribute_ordinal_position,
       attribute_seed.attribute_description,
       attribute_seed.attribute_data_type,
       attribute_seed.attribute_nullability,
       attribute_seed.is_natural_key,
       TRUE
  FROM core.object AS object
 CROSS JOIN (
        VALUES
            (1, 'customer_id', 'Customer business identifier', 'BIGINT', FALSE, TRUE),
            (2, 'customer_name', 'Customer display name', 'VARCHAR(200)', TRUE, FALSE)
       ) AS attribute_seed(
           attribute_ordinal_position,
           attribute_name,
           attribute_description,
           attribute_data_type,
           attribute_nullability,
           is_natural_key
       )
 WHERE object.object_schema IN (
           'source_demo', 'bronze_demo', 'silver_demo', 'gold_demo'
       );

INSERT INTO core.ingestion_object_mapping (
    source_object_id,
    target_object_id
)
SELECT source_object.object_id,
       target_object.object_id
  FROM (
        VALUES
            ('source_demo', 'customer', 'bronze_demo', 'customer'),
            ('bronze_demo', 'customer', 'silver_demo', 'customer'),
            ('silver_demo', 'customer', 'gold_demo', 'dim_customer')
       ) AS mapping_seed(
           source_schema,
           source_name,
           target_schema,
           target_name
       )
 JOIN core.object AS source_object
   ON source_object.object_schema = mapping_seed.source_schema
  AND source_object.object_name = mapping_seed.source_name
 JOIN core.object AS target_object
   ON target_object.object_schema = mapping_seed.target_schema
  AND target_object.object_name = mapping_seed.target_name;

INSERT INTO core.ingestion_attribute_mapping (
    ingestion_object_mapping_id,
    source_object_id,
    target_object_id,
    source_attribute_id,
    target_attribute_id
)
SELECT object_mapping.ingestion_object_mapping_id,
       object_mapping.source_object_id,
       object_mapping.target_object_id,
       source_attribute.attribute_id,
       target_attribute.attribute_id
  FROM core.ingestion_object_mapping AS object_mapping
 JOIN core.attribute AS source_attribute
   ON source_attribute.object_id = object_mapping.source_object_id
 JOIN core.attribute AS target_attribute
   ON target_attribute.object_id = object_mapping.target_object_id
  AND target_attribute.attribute_name = source_attribute.attribute_name;

INSERT INTO core.copy_group (
    tenant_id,
    system_id,
    copy_group_name,
    copy_group_description,
    is_member_group_required
)
SELECT tenant.tenant_id,
       system.system_id,
       'Demo Customer Copy Group',
       'Copies customer records into Bronze',
       TRUE
  FROM core.tenant AS tenant
 CROSS JOIN core.system AS system
 WHERE tenant.tenant_code = 'DEMO_TENANT'
   AND system.system_code = 'DEMO_CUSTOMER_SYSTEM';

INSERT INTO core.member_group (
    tenant_id,
    system_id,
    member_group_name,
    member_group_description
)
SELECT tenant.tenant_id,
       system.system_id,
       'Demo Customer Members',
       'Customer copy membership'
  FROM core.tenant AS tenant
 CROSS JOIN core.system AS system
 WHERE tenant.tenant_code = 'DEMO_TENANT'
   AND system.system_code = 'DEMO_CUSTOMER_SYSTEM';

INSERT INTO core.copy_group_control (
    copy_group_id,
    member_group_id,
    tenant_id,
    system_id
)
SELECT copy_group.copy_group_id,
       member_group.member_group_id,
       copy_group.tenant_id,
       copy_group.system_id
  FROM core.copy_group AS copy_group
 JOIN core.member_group AS member_group
   ON member_group.tenant_id = copy_group.tenant_id
  AND member_group.system_id = copy_group.system_id
 WHERE copy_group.copy_group_name = 'Demo Customer Copy Group'
   AND member_group.member_group_name = 'Demo Customer Members';

INSERT INTO core.copy (
    copy_group_id,
    ingestion_object_mapping_id,
    chunk_type_id,
    copy_source_file_name,
    copy_source_file_pattern,
    copy_source_file_delimiter,
    source_file_type_id,
    copy_source_order,
    source_data_operation_id,
    target_data_operation_id
)
SELECT copy_group.copy_group_id,
       object_mapping.ingestion_object_mapping_id,
       chunk_type.chunk_type_id,
       'customer.parquet',
       'customer*.parquet',
       ',',
       file_type.file_type_id,
       1,
       source_operation.data_operation_id,
       target_operation.data_operation_id
  FROM core.copy_group AS copy_group
 CROSS JOIN reference.chunk_type AS chunk_type
 CROSS JOIN reference.file_type AS file_type
 CROSS JOIN reference.data_operation AS source_operation
 CROSS JOIN reference.data_operation AS target_operation
 JOIN core.object AS source_object
   ON source_object.object_schema = 'source_demo'
  AND source_object.object_name = 'customer'
 JOIN core.object AS target_object
   ON target_object.object_schema = 'bronze_demo'
  AND target_object.object_name = 'customer'
 JOIN core.ingestion_object_mapping AS object_mapping
   ON object_mapping.source_object_id = source_object.object_id
  AND object_mapping.target_object_id = target_object.object_id
 WHERE copy_group.copy_group_name = 'Demo Customer Copy Group'
   AND chunk_type.chunk_type_name = 'Full'
   AND file_type.file_type_name = 'Parquet'
   AND source_operation.data_operation_name = 'Read'
   AND target_operation.data_operation_name = 'Write';

INSERT INTO core.process_group (
    tenant_id,
    system_id,
    zone_id,
    process_group_name,
    process_group_description,
    copy_group_id
)
SELECT copy_group.tenant_id,
       copy_group.system_id,
       zone.zone_id,
       'Demo Customer Silver Processing',
       'Conforms customer records in Silver',
       copy_group.copy_group_id
  FROM core.copy_group AS copy_group
 CROSS JOIN reference.zone AS zone
 WHERE copy_group.copy_group_name = 'Demo Customer Copy Group'
   AND zone.zone_code = 'silver';

INSERT INTO core.process (
    connection_id,
    object_id,
    process_execution_order,
    process_location,
    process_executable,
    process_type_id,
    process_group_id
)
SELECT object.connection_id,
       object.object_id,
       1,
       '/Workspace/Demo/Customer',
       'build_silver_customer',
       process_type.process_type_id,
       process_group.process_group_id
  FROM core.object AS object
 CROSS JOIN reference.process_type AS process_type
 CROSS JOIN core.process_group AS process_group
 WHERE object.object_schema = 'silver_demo'
   AND object.object_name = 'customer'
   AND process_type.process_type_name = 'Notebook'
   AND process_group.process_group_name = 'Demo Customer Silver Processing';

SELECT tenant_id,
       tenant_code,
       tenant_name
  FROM core.tenant
 WHERE tenant_code IN ('DEMO_TENANT', 'DEMO_GDS_TENANT')
 ORDER BY tenant_code;
