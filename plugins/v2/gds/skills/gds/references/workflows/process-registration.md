# Process Registration

Process and Process Group metadata comes after Code Generation only when the user supplies real orchestration details: artifact location/path, executable name, target Object, source System, Process type, dependency order, and any required Copy Group.

Before authoring, derive known values from applied Code, Mapping, and Metadata. Ask one consolidated question for only the missing required details. Then present the resolved artifact-to-Process assignment and dependency order and wait for confirmation. Reconfirm if that assignment changes. This intake is required in every interaction mode.

Do not infer triggers, scheduling, file grouping, or paths. Triggers are orchestration ownership. Several System-specific Process rows may reference the same combined artifact; distinct artifacts may run separately according to user-supplied orchestration metadata.

Author complete records through a Metadata Change Set, preserve existing active metadata, and apply once. Generated code remains a manual handoff; the plugin never deploys it.
