# atlas terminology

Use these terms consistently. Load the affected [metadata table reference](metadata/index.md) for field-level details.

| Term | Meaning |
|---|---|
| Tenant | An organization that owns data, such as a company, line of business or department; the ownership and authorization scope for metadata and Projects. |
| Tenant Code | Stable human-readable Tenant key, unique everywhere; distinct from Tenant name and database ID. |
| Source Tenant | Owner of an Object's data/metadata, independent of physical storage placement. See [Object ownership](metadata/tables/object.md#ownership-and-physical-identity), including explicitly mixed targets. |
| Physical placement | Registered Tenant/System/Connection and schema/name identifying where an Object resides. A schema and name are unique within their Connection, so all five parts name one Object. Endpoint Tenant codes use this identity; see [field distinctions](metadata/tables/object.md#ownership-and-physical-identity). |
| System | One source application or database of one Tenant, such as its HR application, used by Connections and metadata groups. System Code is unique everywhere. `system_type_code` gives its kind of source, such as SQL, FILE or API. |
| Connection | One running instance of a System, such as the HR database of one country, and its registered access/placement definition. Its key is Tenant Code + System Code + Connection Code; Connection Code is unique within its Tenant and System. `connection_type_code` gives its technology, such as SQL_SERVER or ORACLE. |
| Instance | A Connection of a System. Instances have the same or very similar tables but their own rows and their own id numbering: employee 1001 in two countries' instances are different people. A reference points into its own instance. Different Systems number their own rows too, yet one System can refer to another's records, often a shared list. Judge that from the whole picture: what each System is, the names and descriptions of its Objects and Attributes, Context and the data. For example, when System RD is a file listing legal entities, `legal_entity_code` or `legal_entity_name` columns in other Systems refer to it. |
| GDS Connection | The owner's explicitly configured Global Data Store Connection. A generic GDS flag alone does not select it. |
| Object | A physical table/file/view or other registered Object Type at a Connection. |
| Attribute | A field/column of an Object. |
| Row grain | What one record represents, including any entity, event, line or time boundary supported by evidence. |
| Inferred data type | Evidence-supported logical interpretation of an Attribute's values, stored separately from its physical data type. Sample-based conclusions retain their scope and limitations. |
| Physical description correction | Improving physical Object descriptions, Attribute descriptions and Attribute inferred data types in shared Metadata. Scope may come from Tenant/System selection or Project Input Scope; writes are Metadata Change Sets. |
| Project enrichment | Project-owned Object/Attribute descriptions, inferred types and natural-key, primary-key, nullability and PII findings (`object_enrichment`, `attribute_enrichment`). Written through Project Change Sets; never changes physical Metadata. The web app calls this workflow Metadata Enrichment. |
| Custom SELECT expression | Attribute custom code replacing one complete SELECT item during SQL Source extraction or Bronze loading. Includes any required cast and output alias; blank code selects the column unchanged. See [Attribute rules](metadata/tables/attribute.md#custom-select-expressions). |
| Output alias | Name produced by a SELECT expression; distinct from the registered Attribute name and its metadata identity. |
| Zone | Registered layer classification. GDS (Global Data Store) is the Databricks lakehouse. Its own codes (`GDS / GDS / GDS`) say only where a lake Object is stored; the data still belongs to its Source Tenant, and a Bronze Object's business System is the System of its source Objects. `source`: in its original system, outside the lake. `bronze`: a raw copy in the lake, with its source's meaning. `silver`: the Logical model: each kind of data in one clean design across Systems and instances. `gold`: the Dimensional model: facts and dimensions built from silver. |
| Natural key | Complete business identifier used to match an ID-free record. Use the published normalization. |
| Metadata Change Set | Tenant-owned pending physical metadata and Copy/Process configuration. It contains no Project records. |
| Project | Tenant-owned governed aggregate containing scope, modeling sections, and revision. |
| Project Change Set | Pending Project records; it cannot change physical metadata. |
| Subject Area | Named business capability, such as Sales or Billing, over Bronze Input Scope Objects; an Object may belong to several. A focus window: it chooses the Objects a Logical or Dimensional Build works on and is never modeling evidence. See [Subject Areas](project/subject-areas.md). |
| Unassigned Object | Active Bronze Input Scope Object with no active membership in an active Subject Area. It is worked out, not stored. |
| Build / Optimize | The two ways of modeling one Logical or Dimensional model. Build works one Subject Area at a time; Optimize improves existing Entities across the model without an area. |
| Logical Entity / Attribute | A modeled business occurrence and its fields. Physical lineage uses typed sources; see [Logical records](project/logical.md). |
| Dimensional Entity / Attribute | An analytical fact, dimension or bridge and its fields, with eligible Silver lineage or justified generation. [Dimensional records](project/dimensional.md) has distinct roles, grain, measure and history fields. |
| Conformed dimension | Shared analytical context whose meaning, identity and relevant values/history agree across processes; matching names alone is insufficient. |
| Role-playing dimension | One dimension used in distinct roles, such as OrderDate and ShipDate, through separate keys/relationships rather than copied definitions. |
| Type 1 / Type 2 | Overwriting changing values versus retaining row versions. The framework supports both and populates Type 2 fields using natural keys; [history rules](dimensional-build/history.md) define analytical choice, lookup time and SQL omissions. |
| Context | Durable user-supplied/documented rule or evidence in a Context Group/Record. Used when useful; not a mandatory substitute for absent physical lineage. See [Context records](project/context.md). |
| Surrogate key | Generated target identity, separate from business identity. Atlas defaults to a first-column BIGINT own surrogate; FKs are mapped values. See [keys/audit](project/keys-and-audit.md). |
| Business-key tuple | Complete set of facts identifying an occurrence, including source namespace or time when required; components need not be individually unique. |
| Generated / standalone structure | Intentionally produced without a physical source, such as a calendar or fixed reference set. Its meaning and population are explained; no fictitious source is required. |
| Guided mode | Default interaction inside a modeling skill: explain and work through coherent parts. A full source-to-Logical request prefers Profiling → Enrichment → Analysis → Logical, reusing valid results. Same skill, records and rules as Grill Me. |
| Grill Me mode | Requested interview inside the same modeling skill: inspect scope and evidence, ask one consequential decision at a time with a recommended answer, test it with scenarios and develop agreed parts. Older workspaces may call it custom build mode. |
| Investigation | Read-only explanation, debugging or reverse engineering of existing data, models or code; handled by the investigate skill. Older workspaces may label it the Custom workflow. Grants no new permissions. |
| Foundational metadata | Lane, Tenant, System, and Connection context; read-only through this change-set surface. |
| Reference metadata | Registered classification/operation values used by editable records; read-only through this surface. |
| Ingestion Object Mapping | Source-to-Bronze link used by Copy selection and provenance. Multiple Source Objects may share a Bronze target: when several instances load one Bronze Object, an id can repeat once per instance, and the load adds a column just before the technical columns whose values name the instance (an instance, database, member firm or file code or name). |
| Batch column (`GDSBatchID`) | With `GDSBatchID`, each load appends its new and changed rows under a higher batch id, so one record can appear in several loads; its row with the highest `GDSBatchID` is current. A Bronze Object without it is replaced on each load and matches its source. |
| Ingestion Attribute Mapping | Optional reference correspondence; usually empty and not used by the current framework to drive column selection or transformation. |
| Bronze projection | Columns and expressions selected by Bronze metadata from landed data. May omit incoming fields, combine values, or add constants. |
| Landing | Intermediate file stage between Source extraction/transfer and Bronze loading. It adds no Object Zone to the current metadata contract. |
| Landing naming | Filename/pattern values consumed by the landing writer and Bronze reader; their exact usage comes from the applicable framework. |
| Framework contract | Confirmed behavior of the code consuming metadata for a given connector/version, including defaults and substitution rules. Field names alone do not establish it. |
| Copy Group | Named collection of Copy operations within a Tenant/System. Inactive groups skip all their Copies. |
| Member Group | Optional filter applied to a Copy Group through Copy Group Control. Members provide codes and Attribute names. Use only on explicit request; default is_member_group_required=false. |
| Member | One filter value in a Member Group: a code plus the Attribute it filters. Natural key is Member Group + Member Code. Editable through Metadata Change Sets; configure only on explicit request. |
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
| Target registration | Derive Silver/Gold Object and Attribute metadata plus local creation DDL from selected applied modeled Entities. Metadata Apply registers definitions; it does not execute DDL or change modeled ownership. |
| Entity ownership | Mapping and Code belong to a schema-qualified Logical or Dimensional Entity. Target registration is a separate operational handoff; see [Entity ownership](project/entity-ownership.md). |
| Mapping branch | One schema-qualified modeled Entity and originating source System, with Object steps and per-Attribute population rules. A Logical Entity has a branch per System its own source tables come from (Bronze through ingestion lineage); a Dimensional Entity per System its Logical sources are completely mapped from. Context never creates a branch. Several branches can feed one target; Code Generation decides their file grouping. |
| Object / Attribute transformation | Object steps define relational operations, grain and branch behavior; Attribute rules define individual values or database/framework generation. See the shared [Mapping templates](project/mapping-documents.md). |
| Complete Mapping view | Derived Mapping instructions plus resolved target/source metadata, modeled column definitions and Object dependency orders. Coding and Validation consume it without reconstructing upstream model design; not another editable dataset. Source-System list order does not define precedence or execution. |
| Code artifact | One modeled target's named generated file and content. Its Project record is separate from local file placement and does not execute/deploy code. See [Code records](project/generated-code.md). |
| Code source-System assignment | Separate record linking a contributing System to an artifact. Every active mapped System for an authored target has exactly one active assignment; combined files can have several. |
| Validation Group / Check | Project-owned, System-associated definitions: a purposeful collection and its individual SQL assertions. [Validation records](project/validation.md) store queries/expected operands, not execution results; association alone does not filter queried rows. |
| Transformation output / loaded target | Rows produced before persistence versus rows stored after framework loading. [Check design](validation/check-design.md) distinguishes their populations and generated-field responsibilities. |
| Definition validation / context execution | Structural and semantic checks of authored records versus running SQL and evaluating its expected result. Stage/Validate/Apply does not run business contexts. |
| SQL policy | User's choice about executing evidence queries; does not grant server permissions. |
| SQL environment | Selected registered execution environment: dev, qa, stg, prod. |
| Query scope | Exact Objects, Attributes, environment, batch selections and measurement context used for evidence; governed by the shared [query-scope guide](query-scope.md). |
| Relationship candidate | A possible connection supported by names, metadata or business context; it still needs evaluation. |
| Inferred cardinality | Intended multiplicity from Analysis's from endpoint to its to endpoint, stored as `inferred_cardinality`. May be unknown; independent of measured counts. |
| Observed cardinality | Multiplicity evidenced in the inspected population; distinguish it from the intended business rule and optional participation. See [finding relationships](logical-build/find-relationships.md). |
| Tenant Lock | Server-governed write lease; distinct from Object/Attribute protection flags. |
| Locked / unlocked | Content protection state; unlocked records still require valid authoring intent and eligibility. See [record state](record-state.md) for inherited protection and nested locks. |
| Inactive / deprecated | Preserved lifecycle history, not deletion or automatic eligibility for new active dependencies. See [record state](record-state.md). |

The user may say "site" for Tenant. Resolve ambiguity when it could instead mean a deployment or connection. Do not silently equate ownership with physical placement.

Source: current GDS `CONTEXT.md` and the Metadata Snapshot record contracts. Field-specific nuances live on the table pages.
