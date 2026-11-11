# Typesense MCP

A configurable MCP server that exposes read-only search over one or more Typesense
collections. It is designed around paragraph-level TEI indexes such as
`kalbeck-tagebuch-static`, with nested entity arrays for persons, places,
organizations and bibliographic entities.

## Tools

- `list_collections`: discover enabled collections and their search/facet config.
- `search_documents`: full-text search with entity-ID and optional numeric-date filters.
- `get_search_facets`: retrieve facet values/counts for a query and current filters.
- `get_document`: retrieve a single Typesense document by ID.

The server only exposes collections explicitly listed in `TYPESENSE_COLLECTIONS_JSON`.
It does not expose arbitrary Typesense queries or write operations.

## Requirements

- Python 3.12+
- A Typesense server
- A Typesense API key with search-only permissions for the configured collections

## Run locally

```bash
uv run typesense-mcp
```

The MCP endpoint defaults to `http://localhost:8000/mcp`.

For development, you can also run:

```bash
uv run fastmcp run src/typesense_mcp/server.py --transport http --host 0.0.0.0 --port 8000
```

```bash
uv run fastmcp inspect src/typesense_mcp/server.py
```

## Configuration

[TYPESENSE_COLLECTIONS_JSON](src/typesense_mcp/config.py) is a JSON object keyed by Typesense collection name.
Each collection supports:

| Setting | Meaning |
|---|---|
| `query_by` | Ordered Typesense text fields used for full-text search |
| `default_facets` | Allowed facet fields; these must be facetable in the Typesense schema |
| `entity_fields` | Maps MCP filter names to nested entity parent fields |
| `date_field` | Optional numeric field used for inclusive date bounds |
| `facet_return_parent` | Optional nested facet fields whose parent object Typesense should return |
| `result_fields` | Optional allowlist of fields returned to the model |
| `max_facet_values` | Default maximum facet values |
| `sort_by` | Optional Typesense sort expression |
| `description` | Human-readable collection description |

Add another collection as another top-level JSON entry. It can use different
text fields, facet names and date fields.

## Nested entity fields

The implementation expects the shape used in the supplied indexer:

```json
"person_entities": [
  {"id": "person_123", "label": "Karl Kraus"}
]
```

It facets on `person_entities.id` and filters with Typesense nested-object syntax.
`facet_return_parent` asks Typesense to include the parent entity object in facet
results so the model can see labels alongside IDs.

Verify nested filtering/faceting against the Typesense server version in use.
Nested fields must be enabled in the collection schema, and the relevant nested
fields must be facetable.

## Deployment notes

- Put this behind HTTPS (for example nginx or a platform ingress).
- Require authentication at the MCP gateway / reverse proxy, or add an
  authentication layer appropriate to your ChatGPT MCP connection.
- Use a read-only Typesense key scoped to only the required collections.
- Do not expose the Typesense admin key.
- Restrict request sizes and apply rate limits at the reverse proxy.
- Set `MCP_PATH` to `/mcp` unless your hosting environment requires another path.

## Example conversational use

1. “Search the Kalbeck diary for references to Brahms.”
2. “Show me the most frequent persons in those results.”
3. “Restrict it to paragraphs mentioning person ID `...`.”
4. “Retrieve the full indexed paragraph with ID `...`.”

The MCP returns paragraph records and source URLs, so the assistant can cite and
link back to the edition. It does not infer entity IDs from names; resolve names
through facets or your authority data first.
