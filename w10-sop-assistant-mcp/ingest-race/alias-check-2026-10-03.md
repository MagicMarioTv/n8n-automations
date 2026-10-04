# Alias check, 10/3/2026

Question: can the n8n Qdrant vector store node (n8n 2.35.7, `@langchain/qdrant` 1.0.1) search through a Qdrant alias?

Method: a throwaway workflow (`TEMP alias probe`, execution 228, production mode, deleted afterwards). It created alias `probe_alias` pointing at `sop_corpus`, searched through the alias with the vector store node in load mode, listed collections and aliases, then deleted the alias. It never deleted a collection.

Result, node by node:

| Node | Output |
|---|---|
| Create Alias | `{"result": true, "status": "ok"}` |
| Search Through Alias | **ERROR: Bad request - please check your parameters** |
| List Collections | `{"collections": [{"name": "sop_corpus"}]}` |
| List Aliases | `{"aliases": [{"alias_name": "probe_alias", "collection_name": "sop_corpus"}]}` |
| Delete Alias | `{"result": true, "status": "ok"}` |
| Aliases After | `{"aliases": []}` |

Why, from the library source (`@langchain/qdrant@1.0.1`, `dist/vectorstores.js`): every search calls `ensureCollection()`, which lists real collections with `getCollections()` and calls `createCollection()` when the name is not among them. Aliases are not collections, so the search tries to create `probe_alias`, and Qdrant rejects it because an alias already holds the name. The same function explains the ingest race: a search that lands after `Reset Collection` deletes `sop_corpus` creates an empty one and searches it (zero passages), and two creators racing for the name produce `Conflict`.

Consequence: the alias swap planned in w9's Next does not work with this node. Swapping an alias named `sop_corpus` would break every query.
