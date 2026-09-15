# atlas terminology

Use these terms consistently. Load the affected [metadata table reference](metadata/index.md) for field-level details.

| Term | Meaning |
|---|---|
| Tenant | Ownership and authorization scope for metadata and Models. |
| Tenant Code | Stable human-readable Tenant key; distinct from Tenant name and database ID. |
| Source Tenant | Owner of an Object's data/metadata, independent of physical storage placement. See [Object ownership](metadata/tables/object.md#ownership-and-physical-identity), including explicitly mixed targets. |
| Physical placement | Registered Tenant/System/Connection and schema/name identifying where an Object resides. Endpoint Tenant codes use this identity; see [field distinctions](metadata/tables/object.md#ownership-and-physical-identity). |
| System | Registered source/application context used by Connections and metadata groups. |
| Connection | Registered access/placement definition; its key is Tenant Code + System Code + Connection Code. |
| GDS Connection | The owner's explicitly configured Global Data Store Connection. A generic GDS flag alone does not select it. |
| Object | A physical table/file/view or other registered Object Type at a Connection. |
| Attribute | A field/column of an Object. |
| Row grain | What one record represents, including any entity, event, line or time boundary supported by evidence. |
| Inferred data type | Evidence-supported logical interpretation of an Attribute's values, stored separately from its physical data type. Sample-based conclusions retain their scope and limitations. |
| Metadata enrichment | Improving Object descriptions, Attribute descriptions and Attribute inferred data types. Scope may come from Tenant/System selection or Model Input Scope; writes remain Metadata changes. |
| Custom SELECT expression | Attribute custom code replacing one complete SELECT item during SQL Source extraction or Bronze loading. Includes any required cast and output alias; blank code selects the column unchanged. See [Attribute rules](metadata/tables/attribute.md#custom-select-expressions). |
| Output alias | Name produced by a SELECT expression; distinct from the registered Attribute name and its metadata identity. |
| Zone | Registered layer classification. Object authoring uses source, bronze, silver, gold. |
| Natural key | Complete business identifier used to match an ID-free record. Use the published normalization. |
| Metadata Change Set | Tenant-owned pending physical metadata and Copy/Process configuration. It contains no Model records. |
| Model | Tenant-owned governed aggregate containing scope, modeling sections, and revision. |
| Model Change Set | Pending Model records; it cannot change physical metadata. |
| Concept / Conceptual Object | Business meaning represented in a Model, independent of a particular physical Object. Several Objects may support one concept. See [business concepts](logical-build/business-concepts.md). |
| Conceptual Relationship | Business association between Concepts, with direction, cardinality and an explained basis. Its [record contract](model/conceptual.md) differs from physical Attribute-level Analysis. |
| Conceptual support | Nested evidence linking a Concept or Conceptual Relationship to an actual scoped Object or applicable Assertion Record. A support is not a physical join or a separate Change Set dataset. |
| Logical Entity / Attribute | A modeled business occurrence and its fields. Physical lineage uses typed sources; see [Logical records](model/logical.md). |
| Dimensional Entity / Attribute | An analytical fact, dimension or bridge and its fields, with eligible Silver lineage or justified generation. [Dimensional records](model/dimensional.md) has distinct roles, grain, measure and history fields. |
| Conformed dimension | Shared analytical context whose meaning, identity and relevant values/history agree across processes; matching names alone is insufficient. |
| Role-playing dimension | One dimension used in distinct roles, such as OrderDate and ShipDate, through separate keys/relationships rather than copied definitions. |
| Type 1 / Type 2 | Overwriting changing values versus retaining row versions. The framework supports both and populates Type 2 fields using natural keys; [history rules](dimensional-build/history.md) define analytical choice, lookup time and SQL omissions. |
| Submodel | Business grouping/view of shared Entities through memberships. It does not create separate copies or isolate cross-group relationships. |
| Assertion | Durable user-supplied/documented rule or evidence in an Assertion Document/Record. Used when useful; not a mandatory substitute for absent physical lineage. See [Assertions](model/assertions.md). |
| Surrogate key | Generated target identity, separate from business identity. Atlas defaults to a first-column BIGINT own surrogate; FKs are mapped values. See [keys/audit](model/keys-and-audit.md). |
| Business-key tuple | Complete set of facts identifying an occurrence, including source namespace or time when required; components need not be individually unique. |
| Generated / standalone structure | Intentionally produced without a physical source, such as a calendar or fixed reference set. Its meaning and population are explained; no fictitious source is required. |
| Guided build workflow | Dedicated skill following defined phases. Logical Guided follows Profiling → Analysis → Conceptual → Logical, checking existing results and reuse/redo choices. Dimensional Guided will have its own agreed sequence. |
| Grill Me build workflow | Dedicated collaborative modeling skill: inspect scope and evidence, recommend answers, challenge relevant scenarios and develop agreed parts. Shares domain rules with Guided, with its own interaction and sequence. Previously called custom build mode; distinct from the top-level Custom workflow. |
| Custom workflow | Outcome-driven investigation or work outside named workflows, such as debugging, reverse engineering or explaining existing data/models. It selects only needed inputs/methods; no new permissions or compulsory phase sequence. |
| Foundational metadata | Project, Tenant, System, and Connection context; read-only through this change-set surface. |
| Reference metadata | Registered classification/operation values used by editable records; read-only through this surface. |
| Ingestion Object Mapping | Source-to-Bronze link used by Copy selection and provenance. Multiple Source Objects may share a Bronze target. |
| Ingestion Attribute Mapping | Optional reference correspondence; usually empty and not used by the current framework to drive column selection or transformation. |
| Bronze projection | Columns and expressions selected by Bronze metadata from landed data. May omit incoming fields, combine values, or add constants. |
| Landing | Intermediate file stage between Source extraction/transfer and Bronze loading. It adds no Object Zone to the current metadata contract. |
| Landing naming | Filename/pattern values consumed by the landing writer and Bronze reader; their exact usage comes from the applicable framework. |
| Framework contract | Confirmed behavior of the code consuming metadata for a given connector/version, including defaults and substitution rules. Field names alone do not establish it. |
| Copy Group | Named collection of Copy operations within a Tenant/System. Inactive groups skip all their Copies. |
| Member Group | Existing optional grouping for control state. Its execution behavior is deferred; default is_member_group_required to false on new Copy Groups. |
| Member | Table identified for future Atlas coverage; its schema, keys and Member Group relationship remain to be defined. |
| Copy Group Control | Optional initial-load filter date and framework-maintained run state for a Copy Group and optional Member Group. New run values start null. |
| Copy | Registered Source-to-target copy configuration within a Copy Group. |
| Copy order | Sorting value currently used like ORDER BY, with agreed new-record default 1. It does not currently define execution stages or success barriers. |
| Chunk Type | Registered logic splitting a large initial extraction into smaller source queries. Applicable scope and usage come from its description; select only when the user requests chunking. |
| Data Operation | Registered target loading function; Copy Into appends. The Copy's source-operation reference is required but unused at runtime. |
| Initial/incremental filter | Copy-level query fragment selected using control state. Saved text includes WHERE and is inserted as supplied. Empty adds nothing; target loading behavior is independent. |
| Process Group | Tenant/System/Zone grouping of Processes associated with a Copy Group. |
| Process Group dependency order | New group field with agreed default 1, mutable outside its natural key. Defines sequential dependency levels within a Zone phase; equal-level groups pool Processes across Systems. Requires the Atlas-compatible backend; existing installations need operator order review. |
| Process | Registered executable, execution order, location, type, and associated Object. |
| Process metadata workflow | Connect applied generated artifacts to Process Groups, Copy Groups and target Objects using confirmed runtime locations and invocation order. Records belong to a Metadata Change Set; Code storage and registration have no automatic synchronization. |
| Process Type | Type of the logic file: SQL or Python in the confirmed framework. Process location holds its path; executable holds its filename including .sql or .python. |
| Pipeline selectors | Trigger inputs: one Tenant name, comma-separated System names, optional Copy Group and Member Group. Null group selectors select all applicable groups within scope. |
| Zone phase | Processing selected groups in their group's Zone. All selected Silver work succeeds before Gold starts; the target Object's Zone does not override the group phase. |
| Execution stage | Processes sharing a Process execution order within one Zone phase and Process Group dependency level. Resulting invocations run in parallel and must all succeed before advancement. |
| Shared executable | Same runnable artifact referenced by multiple Process records. Runs once within one execution stage of a pipeline run; intentional references at later stages run again. Artifact matching follows the framework contract. |
| Workspace | Selected absolute working directory containing atlas state and working files. |
| Session | Saved workspace context that can span conversations. |
| Task | One meaningful requested outcome, with its inputs, work, progress, and evidence. |
| Plan | Optional revisable approach inside the task. |
| Snapshot | Exported source state identified by its manifest; installed does not mean verified current. |
| Snapshot catalog | Dataset directory inside a Snapshot: section, data/schema paths, keys and row counts. Use it to locate relevant records and their authoring schemas. |
| Effective result | Snapshot records overlaid with pending changes using complete natural keys. |
| Local Change Set | Sparse draft containing complete proposed records. Related edits accumulate locally before governed submission; omitted applied records remain unchanged. |
| Target registration | Derive Silver/Gold Object and Attribute metadata plus local creation DDL from selected applied modeled Entities. Metadata Apply registers definitions; it does not execute DDL or create Model Bindings. |
| Entity Binding | Workflow assigning Logical Entities to registered Silver Objects or Dimensional Entities to Gold Objects, plus every active modeled Attribute to its target column. Two [Model Binding datasets](model/binding.md) record these assignments; loading expressions belong to Mapping. |
| Mapping branch | One bound target Entity and originating source System, with Object steps and per-Attribute population rules. Several branches can feed one target; Code Generation decides their file grouping. |
| Object / Attribute transformation | Object steps define relational operations, grain and branch behavior; Attribute rules define individual values or database/framework generation. See the shared [Mapping templates](model/mapping-documents.md). |
| Complete Mapping view | Derived Mapping instructions plus resolved target/source metadata, physical column bindings and dependency orders. Coding and Validation consume it without reconstructing upstream model design; not another editable dataset. |
| Code artifact | One modeled target's named generated file and content. Its Model record is separate from local file placement and does not execute/deploy code. See [Code records](model/generated-code.md). |
| Code source-System assignment | Separate record linking a contributing System to an artifact. Every active mapped System for an authored target has exactly one active assignment; combined files can have several. |
| Validation Group / Check | Model-owned, System-associated definitions: a purposeful collection and its individual SQL assertions. [Validation records](model/validation.md) store queries/expected operands, not execution results; association alone does not filter queried rows. |
| Transformation output / loaded target | Rows produced before persistence versus rows stored after framework loading. [Check design](validation/check-design.md) distinguishes their populations and generated-field responsibilities. |
| Definition validation / assertion execution | Structural and semantic checks of authored records versus running SQL and evaluating its expected result. Stage/Validate/Apply does not run business assertions. |
| SQL policy | User's choice about executing evidence queries; does not grant server permissions. |
| SQL environment | Selected registered execution environment: dev, qa, stg, prod. |
| Query scope | Exact Objects, Attributes, environment, batch selections and measurement context used for evidence; governed by the shared [query-scope guide](query-scope.md). |
| Relationship candidate | A possible connection supported by names, metadata or business context; it still needs evaluation. |
| Observed cardinality | Multiplicity evidenced in the inspected population; distinguish it from the intended business rule and optional participation. See [finding relationships](logical-build/find-relationships.md). |
| Tenant Lock | Server-governed write lease; distinct from Object/Attribute protection flags. |
| Locked / unlocked | Content protection state; unlocked records still require valid authoring intent and eligibility. See [record state](record-state.md) for inherited protection and nested locks. |
| Inactive / deprecated | Preserved lifecycle history, not deletion or automatic eligibility for new active dependencies. See [record state](record-state.md). |

The user may say "site" for Tenant. Resolve ambiguity when it could instead mean a deployment or connection. Do not silently equate ownership with physical placement.

Source: current GDS `CONTEXT.md` and the Metadata Snapshot record contracts. Field-specific nuances live on the table pages.
