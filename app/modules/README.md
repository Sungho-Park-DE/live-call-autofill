# Modules

Each folder here is one concept (`<name>_v<N>`, spec in `docs/concepts/`). Modules never import each other — not even another module's public entry — and never import `app/adapters`. They meet only in `app/syncs/`. Other code imports a module only through its `__init__.py`. A module's tests live inside its folder so they are deleted with it.
