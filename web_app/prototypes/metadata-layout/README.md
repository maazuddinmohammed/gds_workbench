# Metadata layout prototype

Throwaway prototype answering: **How should Objects and Attributes appear inside Metadata?**

Three layouts share the same mock Tenant, lock state, Zones, Objects, and Attributes:

- `A`: stacked grids
- `B`: object explorer
- `C`: inline hierarchy

Run from this directory:

```bash
python3 -m http.server 4173
```

Open `http://localhost:4173/?variant=a`. Use the bottom switcher or Left/Right arrow keys.

Visual thesis: calm operational console; dense data, restrained color, obvious lock authority.

Content plan: Tenant and lock context, Metadata navigation, Zone selection, Object/Attribute workspace.

Interaction thesis: Zone transitions, Object selection, explicit mock lock acquisition, URL-backed variant switching.

Delete this directory after a layout decision is captured.
