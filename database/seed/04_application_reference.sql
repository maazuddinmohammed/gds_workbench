-- Stable web-application workflow reference metadata.
-- Safe to replay after a successful canonical install. Contains no prompts,
-- SQL generation content, credentials, connection values, or business data.

INSERT INTO application.workflow_stage (
    model_workflow,
    workflow_execution_mode,
    workflow_stage_code,
    workflow_stage_name,
    workflow_stage_description,
    workflow_stage_order,
    workflow_stage_is_agentic
)
VALUES
    (
        'profiling', NULL, 'profile_attributes', 'Profile Attributes',
        'Run bounded deterministic Attribute profiling.', 10, FALSE
    ),
    (
        'analysis', NULL, 'relationship_validation',
        'Relationship Validation',
        'Validate inferred relationship evidence deterministically.', 10, FALSE
    ),
    (
        'analysis', 'one_shot', 'relationship_inference',
        'Relationship Inference',
        'Infer relationship candidates from one bounded context.', 10, TRUE
    ),
    (
        'analysis', 'tool_assisted', 'relationship_inference',
        'Relationship Inference',
        'Infer relationship candidates with bounded local context tools.',
        10, TRUE
    ),
    (
        'analysis', 'detailed_coverage', 'candidate_finder',
        'Candidate Finder',
        'Find candidate relationship endpoints for covered Objects.', 10, TRUE
    ),
    (
        'analysis', 'detailed_coverage', 'relationship_resolver',
        'Relationship Resolver',
        'Resolve complete relationship proposals for covered Objects.', 20, TRUE
    ),
    (
        'analysis', 'detailed_coverage', 'whole_slice_reconciler',
        'Whole-slice Reconciler',
        'Reconcile the complete affected Analysis slice.', 30, TRUE
    ),
    (
        'analysis', 'detailed_coverage', 'analysis_reviewer',
        'Analysis Reviewer',
        'Review the complete Analysis candidate without mutating it.', 40, TRUE
    ),
    (
        'conceptual', NULL, 'backend_validation', 'Backend Validation',
        'Validate the normalized Conceptual candidate deterministically.',
        100, FALSE
    ),
    (
        'conceptual', 'one_shot', 'candidate_authoring',
        'Candidate Authoring',
        'Author one complete Conceptual candidate from bounded context.',
        10, TRUE
    ),
    (
        'conceptual', 'tool_assisted', 'candidate_authoring',
        'Candidate Authoring',
        'Author one complete Conceptual candidate with bounded local tools.',
        10, TRUE
    ),
    (
        'conceptual', 'detailed_coverage', 'object_contribution',
        'Object Contribution',
        'Produce explicit contributions for covered physical Objects.', 10, TRUE
    ),
    (
        'conceptual', 'detailed_coverage', 'entity_consolidation',
        'Entity Consolidation',
        'Consolidate covered Object contributions into stable entities.',
        20, TRUE
    ),
    (
        'conceptual', 'detailed_coverage', 'entity_attribute_detail',
        'Entity and Attribute Detail',
        'Author complete detail for consolidated entities.', 30, TRUE
    ),
    (
        'conceptual', 'detailed_coverage',
        'relationship_candidate_derivation', 'Relationship Candidate Derivation',
        'Derive bounded relationship candidates from matching evidence.',
        40, FALSE
    ),
    (
        'conceptual', 'detailed_coverage',
        'relationship_cardinality_refinement',
        'Relationship and Cardinality Refinement',
        'Refine relationship meaning and cardinality from bounded evidence.',
        50, TRUE
    ),
    (
        'conceptual', 'detailed_coverage', 'whole_model_reconciliation',
        'Whole-model Reconciliation',
        'Reconcile the complete Conceptual candidate and Submodel membership.',
        60, TRUE
    ),
    (
        'logical', NULL, 'policy_projection', 'Policy Projection',
        'Apply configured Logical audit-column policy deterministically.',
        50, FALSE
    ),
    (
        'logical', NULL, 'backend_validation', 'Backend Validation',
        'Validate the normalized Logical candidate deterministically.',
        100, FALSE
    ),
    (
        'logical', 'one_shot', 'candidate_authoring', 'Candidate Authoring',
        'Author one complete Logical candidate from bounded context.', 10, TRUE
    ),
    (
        'logical', 'tool_assisted', 'candidate_authoring',
        'Candidate Authoring',
        'Author one complete Logical candidate with bounded local tools.',
        10, TRUE
    ),
    (
        'logical', 'detailed_coverage', 'topology_builder',
        'Topology Builder',
        'Propose covered Logical topology with explicit dispositions.', 10, TRUE
    ),
    (
        'logical', 'detailed_coverage', 'topology_reconciler',
        'Topology Reconciler',
        'Reconcile a complete stable Logical Entity ledger.', 20, TRUE
    ),
    (
        'logical', 'detailed_coverage', 'entity_detail_builder',
        'Entity Detail Builder',
        'Author complete detail for each affected Logical Entity.', 30, TRUE
    ),
    (
        'logical', 'detailed_coverage', 'whole_model_reconciliation',
        'Whole-model Reconciliation',
        'Reconcile the complete affected Logical model.', 40, TRUE
    ),
    (
        'logical', 'detailed_coverage', 'validator_worker',
        'Validator Worker',
        'Review one bounded Logical validation package.', 60, TRUE
    ),
    (
        'logical', 'detailed_coverage', 'validator_lead',
        'Validator Lead',
        'Reconcile all Logical validation findings into one repair brief.',
        70, TRUE
    ),
    (
        'dimensional', NULL, 'gold_policy_projection',
        'Gold Policy Projection',
        'Apply configured Gold technical and audit-column policy.', 50, FALSE
    ),
    (
        'dimensional', NULL, 'foreign_key_projection',
        'Foreign-key Projection',
        'Project final role-aware Gold foreign keys deterministically.',
        80, FALSE
    ),
    (
        'dimensional', NULL, 'backend_validation', 'Backend Validation',
        'Validate the normalized Dimensional candidate deterministically.',
        100, FALSE
    ),
    (
        'dimensional', 'one_shot', 'candidate_authoring',
        'Candidate Authoring',
        'Author one complete Dimensional candidate from bounded context.',
        10, TRUE
    ),
    (
        'dimensional', 'tool_assisted', 'candidate_authoring',
        'Candidate Authoring',
        'Author one complete Dimensional candidate with bounded local tools.',
        10, TRUE
    ),
    (
        'dimensional', 'detailed_coverage', 'topology_builder',
        'Topology Builder',
        'Propose covered Dimensional topology with explicit dispositions.',
        10, TRUE
    ),
    (
        'dimensional', 'detailed_coverage', 'topology_reconciler',
        'Topology Reconciler',
        'Reconcile a complete stable Dimensional Entity ledger.', 20, TRUE
    ),
    (
        'dimensional', 'detailed_coverage', 'entity_detail_builder',
        'Entity Detail Builder',
        'Author complete detail for each affected Dimensional Entity.',
        30, TRUE
    ),
    (
        'dimensional', 'detailed_coverage', 'whole_model_reconciliation',
        'Whole-model Reconciliation',
        'Reconcile the complete affected Dimensional model.', 40, TRUE
    ),
    (
        'dimensional', 'detailed_coverage', 'validator_worker',
        'Validator Worker',
        'Review one bounded Dimensional validation package.', 60, TRUE
    ),
    (
        'dimensional', 'detailed_coverage', 'validator_lead',
        'Validator Lead',
        'Reconcile all Dimensional findings into one repair brief.', 70, TRUE
    ),
    (
        'mapping', NULL, 'dependency_validation', 'Dependency Validation',
        'Validate Mapping dependency graphs and write safety.', 80, FALSE
    ),
    (
        'mapping', NULL, 'backend_validation', 'Backend Validation',
        'Validate the normalized Mapping candidate deterministically.',
        100, FALSE
    ),
    (
        'mapping', 'one_shot', 'mapping_authoring', 'Mapping Authoring',
        'Author one complete Mapping candidate from bounded context.', 10, TRUE
    ),
    (
        'mapping', 'tool_assisted', 'mapping_authoring',
        'Mapping Authoring',
        'Author one complete Mapping candidate with bounded local tools.',
        10, TRUE
    ),
    (
        'mapping', 'detailed_coverage', 'header_mapper', 'Header Mapper',
        'Author complete target and source-System Mapping headers.', 10, TRUE
    ),
    (
        'mapping', 'detailed_coverage', 'attribute_mapper',
        'Attribute Mapper',
        'Author complete Attribute Mapping coverage for a header.', 20, TRUE
    ),
    (
        'mapping', 'detailed_coverage', 'target_validator',
        'Target Validator',
        'Review one complete target and source-System Mapping package.',
        30, TRUE
    ),
    (
        'code_generation', NULL, 'sql_generation', 'SQL Generation',
        'Generate SQL from applied Mapping and a selected versioned guide.',
        10, TRUE
    ),
    (
        'code_generation', NULL, 'sql_validation', 'SQL Validation',
        'Validate generated SQL without executing or deploying it.', 20, FALSE
    ),
    (
        'qa', NULL, 'validation_generation', 'Validation Generation',
        'Generate deterministic validation groups and checks from applied Mapping and current Code.',
        10, TRUE
    ),
    (
        'qa', NULL, 'backend_validation', 'Backend Validation',
        'Validate QA scope, assertion shapes, and governed SQL deterministically.',
        20, FALSE
    )
ON CONFLICT ON CONSTRAINT uq_workflow_stage_identity DO NOTHING;

WITH agentic_stage_seed (
    model_workflow,
    workflow_execution_mode,
    workflow_stage_code
) AS (
    VALUES
        ('analysis', 'one_shot', 'relationship_inference'),
        ('analysis', 'tool_assisted', 'relationship_inference'),
        ('analysis', 'detailed_coverage', 'candidate_finder'),
        ('analysis', 'detailed_coverage', 'relationship_resolver'),
        ('analysis', 'detailed_coverage', 'whole_slice_reconciler'),
        ('analysis', 'detailed_coverage', 'analysis_reviewer'),
        ('conceptual', 'one_shot', 'candidate_authoring'),
        ('conceptual', 'tool_assisted', 'candidate_authoring'),
        ('conceptual', 'detailed_coverage', 'object_contribution'),
        ('conceptual', 'detailed_coverage', 'entity_consolidation'),
        ('conceptual', 'detailed_coverage', 'entity_attribute_detail'),
        (
            'conceptual', 'detailed_coverage',
            'relationship_cardinality_refinement'
        ),
        (
            'conceptual', 'detailed_coverage',
            'whole_model_reconciliation'
        ),
        ('logical', 'one_shot', 'candidate_authoring'),
        ('logical', 'tool_assisted', 'candidate_authoring'),
        ('logical', 'detailed_coverage', 'topology_builder'),
        ('logical', 'detailed_coverage', 'topology_reconciler'),
        ('logical', 'detailed_coverage', 'entity_detail_builder'),
        ('logical', 'detailed_coverage', 'whole_model_reconciliation'),
        ('logical', 'detailed_coverage', 'validator_worker'),
        ('logical', 'detailed_coverage', 'validator_lead'),
        ('dimensional', 'one_shot', 'candidate_authoring'),
        ('dimensional', 'tool_assisted', 'candidate_authoring'),
        ('dimensional', 'detailed_coverage', 'topology_builder'),
        ('dimensional', 'detailed_coverage', 'topology_reconciler'),
        ('dimensional', 'detailed_coverage', 'entity_detail_builder'),
        (
            'dimensional', 'detailed_coverage',
            'whole_model_reconciliation'
        ),
        ('dimensional', 'detailed_coverage', 'validator_worker'),
        ('dimensional', 'detailed_coverage', 'validator_lead'),
        ('mapping', 'one_shot', 'mapping_authoring'),
        ('mapping', 'tool_assisted', 'mapping_authoring'),
        ('mapping', 'detailed_coverage', 'header_mapper'),
        ('mapping', 'detailed_coverage', 'attribute_mapper'),
        ('mapping', 'detailed_coverage', 'target_validator'),
        ('code_generation', NULL, 'sql_generation')
)
INSERT INTO application.workflow_stage_variable (
    workflow_stage_id,
    workflow_stage_variable_name,
    workflow_stage_variable_resolver_key,
    workflow_stage_variable_data_type,
    workflow_stage_variable_is_required,
    workflow_stage_variable_description,
    workflow_stage_variable_example,
    workflow_stage_variable_order
)
SELECT stage.workflow_stage_id,
       'stage_context',
       'workflow.' || stage.model_workflow || '.'
           || COALESCE(stage.workflow_execution_mode, 'common') || '.'
           || stage.workflow_stage_code || '.context',
       'json',
       TRUE,
       'Bounded typed context assembled for this workflow stage.',
       '{"schema_version":"1.0","items":[]}'::JSONB,
       10
  FROM agentic_stage_seed AS seed
  JOIN application.workflow_stage AS stage
    ON stage.model_workflow = seed.model_workflow
   AND stage.workflow_execution_mode IS NOT DISTINCT FROM
       seed.workflow_execution_mode
   AND stage.workflow_stage_code = seed.workflow_stage_code
   AND stage.workflow_stage_is_agentic
ON CONFLICT ON CONSTRAINT uq_workflow_stage_variable_name DO NOTHING;

WITH naming_stage_seed (
    model_workflow,
    workflow_execution_mode,
    workflow_stage_code
) AS (
    VALUES
        ('conceptual', 'one_shot', 'candidate_authoring'),
        ('conceptual', 'tool_assisted', 'candidate_authoring'),
        ('conceptual', 'detailed_coverage', 'object_contribution'),
        ('conceptual', 'detailed_coverage', 'entity_consolidation'),
        ('conceptual', 'detailed_coverage', 'entity_attribute_detail'),
        (
            'conceptual', 'detailed_coverage',
            'relationship_cardinality_refinement'
        ),
        (
            'conceptual', 'detailed_coverage',
            'whole_model_reconciliation'
        ),
        ('logical', 'one_shot', 'candidate_authoring'),
        ('logical', 'tool_assisted', 'candidate_authoring'),
        ('logical', 'detailed_coverage', 'topology_builder'),
        ('logical', 'detailed_coverage', 'topology_reconciler'),
        ('logical', 'detailed_coverage', 'entity_detail_builder'),
        ('logical', 'detailed_coverage', 'whole_model_reconciliation'),
        ('dimensional', 'one_shot', 'candidate_authoring'),
        ('dimensional', 'tool_assisted', 'candidate_authoring'),
        ('dimensional', 'detailed_coverage', 'topology_builder'),
        ('dimensional', 'detailed_coverage', 'topology_reconciler'),
        ('dimensional', 'detailed_coverage', 'entity_detail_builder'),
        (
            'dimensional', 'detailed_coverage',
            'whole_model_reconciliation'
        )
)
INSERT INTO application.workflow_stage_variable (
    workflow_stage_id,
    workflow_stage_variable_name,
    workflow_stage_variable_resolver_key,
    workflow_stage_variable_data_type,
    workflow_stage_variable_is_required,
    workflow_stage_variable_description,
    workflow_stage_variable_example,
    workflow_stage_variable_order
)
SELECT stage.workflow_stage_id,
       'naming_instructions',
       'model.naming_instructions',
       'text',
       FALSE,
       'Optional Model naming instructions for authoring and reconciliation.',
       '""'::JSONB,
       20
  FROM naming_stage_seed AS seed
  JOIN application.workflow_stage AS stage
    ON stage.model_workflow = seed.model_workflow
   AND stage.workflow_execution_mode = seed.workflow_execution_mode
   AND stage.workflow_stage_code = seed.workflow_stage_code
   AND stage.workflow_stage_is_agentic
ON CONFLICT ON CONSTRAINT uq_workflow_stage_variable_name DO NOTHING;

WITH repair_stage_seed (
    model_workflow,
    workflow_execution_mode,
    workflow_stage_code
) AS (
    VALUES
        ('analysis', 'one_shot', 'relationship_inference'),
        ('analysis', 'tool_assisted', 'relationship_inference'),
        ('analysis', 'detailed_coverage', 'whole_slice_reconciler'),
        ('conceptual', 'one_shot', 'candidate_authoring'),
        ('conceptual', 'tool_assisted', 'candidate_authoring'),
        (
            'conceptual', 'detailed_coverage',
            'whole_model_reconciliation'
        ),
        ('logical', 'one_shot', 'candidate_authoring'),
        ('logical', 'tool_assisted', 'candidate_authoring'),
        ('logical', 'detailed_coverage', 'whole_model_reconciliation'),
        ('dimensional', 'one_shot', 'candidate_authoring'),
        ('dimensional', 'tool_assisted', 'candidate_authoring'),
        (
            'dimensional', 'detailed_coverage',
            'whole_model_reconciliation'
        ),
        ('mapping', 'one_shot', 'mapping_authoring'),
        ('mapping', 'tool_assisted', 'mapping_authoring'),
        ('mapping', 'detailed_coverage', 'header_mapper'),
        ('mapping', 'detailed_coverage', 'attribute_mapper'),
        ('code_generation', NULL, 'sql_generation'),
        ('qa', NULL, 'validation_generation')
)
INSERT INTO application.workflow_stage_variable (
    workflow_stage_id,
    workflow_stage_variable_name,
    workflow_stage_variable_resolver_key,
    workflow_stage_variable_data_type,
    workflow_stage_variable_is_required,
    workflow_stage_variable_description,
    workflow_stage_variable_example,
    workflow_stage_variable_order
)
SELECT stage.workflow_stage_id,
       'validation_failures',
       'workflow.validation_failures',
       'json',
       FALSE,
       'Safe bounded validation findings from the current Workflow Run.',
       '[]'::JSONB,
       30
  FROM repair_stage_seed AS seed
  JOIN application.workflow_stage AS stage
    ON stage.model_workflow = seed.model_workflow
   AND stage.workflow_execution_mode IS NOT DISTINCT FROM
       seed.workflow_execution_mode
   AND stage.workflow_stage_code = seed.workflow_stage_code
   AND stage.workflow_stage_is_agentic
ON CONFLICT ON CONSTRAINT uq_workflow_stage_variable_name DO NOTHING;

INSERT INTO application.workflow_stage_variable (
    workflow_stage_id,
    workflow_stage_variable_name,
    workflow_stage_variable_resolver_key,
    workflow_stage_variable_data_type,
    workflow_stage_variable_is_required,
    workflow_stage_variable_description,
    workflow_stage_variable_example,
    workflow_stage_variable_order
)
SELECT stage.workflow_stage_id,
       'validation_context',
       'workflow.qa.common.validation_context',
       'json',
       TRUE,
       'Bounded applied Mapping, optional current Code, and applied QA for one frozen System.',
       '{"system_ref":"system_1"}'::JSONB,
       10
  FROM application.workflow_stage AS stage
 WHERE stage.model_workflow = 'qa'
   AND stage.workflow_execution_mode IS NULL
   AND stage.workflow_stage_code = 'validation_generation'
   AND stage.workflow_stage_is_agentic
ON CONFLICT ON CONSTRAINT uq_workflow_stage_variable_name DO NOTHING;

WITH mapping_object_template_stage_seed (
    model_workflow,
    workflow_execution_mode,
    workflow_stage_code
) AS (
    VALUES
        ('mapping', 'one_shot', 'mapping_authoring'),
        ('mapping', 'tool_assisted', 'mapping_authoring'),
        ('mapping', 'detailed_coverage', 'header_mapper')
)
INSERT INTO application.workflow_stage_variable (
    workflow_stage_id,
    workflow_stage_variable_name,
    workflow_stage_variable_resolver_key,
    workflow_stage_variable_data_type,
    workflow_stage_variable_is_required,
    workflow_stage_variable_description,
    workflow_stage_variable_example,
    workflow_stage_variable_order
)
SELECT stage.workflow_stage_id,
       'mapping_object_output_template',
       'workflow.mapping.object_output_template',
       'json',
       FALSE,
       'Selected Mapping Object output-template definition.',
       '{"fields":[]}'::JSONB,
       40
  FROM mapping_object_template_stage_seed AS seed
  JOIN application.workflow_stage AS stage
    ON stage.model_workflow = seed.model_workflow
   AND stage.workflow_execution_mode = seed.workflow_execution_mode
   AND stage.workflow_stage_code = seed.workflow_stage_code
   AND stage.workflow_stage_is_agentic
ON CONFLICT ON CONSTRAINT uq_workflow_stage_variable_name DO NOTHING;

WITH mapping_attribute_template_stage_seed (
    model_workflow,
    workflow_execution_mode,
    workflow_stage_code
) AS (
    VALUES
        ('mapping', 'one_shot', 'mapping_authoring'),
        ('mapping', 'tool_assisted', 'mapping_authoring'),
        ('mapping', 'detailed_coverage', 'attribute_mapper')
)
INSERT INTO application.workflow_stage_variable (
    workflow_stage_id,
    workflow_stage_variable_name,
    workflow_stage_variable_resolver_key,
    workflow_stage_variable_data_type,
    workflow_stage_variable_is_required,
    workflow_stage_variable_description,
    workflow_stage_variable_example,
    workflow_stage_variable_order
)
SELECT stage.workflow_stage_id,
       'mapping_attribute_output_template',
       'workflow.mapping.attribute_output_template',
       'json',
       FALSE,
       'Selected Mapping Attribute output-template definition.',
       '{"fields":[]}'::JSONB,
       50
  FROM mapping_attribute_template_stage_seed AS seed
  JOIN application.workflow_stage AS stage
    ON stage.model_workflow = seed.model_workflow
   AND stage.workflow_execution_mode = seed.workflow_execution_mode
   AND stage.workflow_stage_code = seed.workflow_stage_code
   AND stage.workflow_stage_is_agentic
ON CONFLICT ON CONSTRAINT uq_workflow_stage_variable_name DO NOTHING;

INSERT INTO application.workflow_stage_variable (
    workflow_stage_id,
    workflow_stage_variable_name,
    workflow_stage_variable_resolver_key,
    workflow_stage_variable_data_type,
    workflow_stage_variable_is_required,
    workflow_stage_variable_description,
    workflow_stage_variable_example,
    workflow_stage_variable_order
)
SELECT stage.workflow_stage_id,
       'sql_generation_guide',
       'workflow.code_generation.sql_generation_guide',
       'text',
       TRUE,
       'Selected immutable SQL generation guide content.',
       '""'::JSONB,
       40
  FROM application.workflow_stage AS stage
 WHERE stage.model_workflow = 'code_generation'
   AND stage.workflow_execution_mode IS NULL
   AND stage.workflow_stage_code = 'sql_generation'
   AND stage.workflow_stage_is_agentic
ON CONFLICT ON CONSTRAINT uq_workflow_stage_variable_name DO NOTHING;
