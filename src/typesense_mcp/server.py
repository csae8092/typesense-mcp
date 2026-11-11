from __future__ import annotations

import os
import re
from typing import Any

import typesense
from fastmcp import FastMCP
from typesense.exceptions import ObjectNotFound

from typesense_mcp.config import TYPESENSE_COLLECTIONS_JSON

mcp = FastMCP(
    "Typesense Full-text Search",
    instructions=(
        "Search configured Typesense collections. Use search_documents for full-text "
        "search and filters; use get_search_facets to explore available facet values. "
        "Entity filters accept stable entity IDs, not display labels. A collection's "
        "date filter is available only when date_field is configured."
    ),
)

_SAFE_FIELD = re.compile(r"^[A-Za-z0-9_.-]+$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]+$")


def _load_collections() -> dict[str, dict[str, Any]]:
    configs = TYPESENSE_COLLECTIONS_JSON

    for name, config in configs.items():
        if not isinstance(config, dict):
            raise TypeError(f"Configuration for {name!r} must be an object")
        config.setdefault("query_by", ["title", "full_text"])
        config.setdefault("default_facets", [])
        config.setdefault("entity_fields", {})
        config.setdefault("result_fields", [])
        if not isinstance(config["query_by"], list) or not config["query_by"]:
            raise RuntimeError(f"{name}: query_by must be a non-empty list")
        for field in config["query_by"]:
            _validate_field(field)
        for facet in config["default_facets"]:
            _validate_field(facet)
        for parent in config["entity_fields"].values():
            _validate_field(parent)
        if config.get("date_field"):
            _validate_field(config["date_field"])
    return configs


def _validate_field(field: str) -> None:
    if not isinstance(field, str) or not _SAFE_FIELD.fullmatch(field):
        raise ValueError(f"Unsafe or invalid Typesense field name: {field!r}")


def _validate_id(value: str) -> str:
    if not _SAFE_ID.fullmatch(value):
        raise ValueError(f"Invalid entity ID: {value!r}")
    return value


def _client() -> typesense.Client:
    return typesense.Client(
        {
            "nodes": [
                {
                    "host": os.environ.get(
                        "TYPESENSE_HOST", "typesense.acdh-dev.oeaw.ac.at"
                    ),
                    "port": os.environ.get("TYPESENSE_PORT", "443"),
                    "protocol": os.environ.get("TYPESENSE_PROTOCOL", "https"),
                }
            ],
            "api_key": "QXrvdzA1egS1JuzjM05QzPkgNXwuesTP",
            "connection_timeout_seconds": int(
                os.environ.get("TYPESENSE_TIMEOUT", "10")
            ),
        }
    )


COLLECTIONS = _load_collections()
client = _client()


def _collection(name: str) -> dict[str, Any]:
    if name not in COLLECTIONS:
        raise ValueError(
            f"Unknown collection {name!r}. Available collections: "
            f"{', '.join(sorted(COLLECTIONS))}"
        )
    return COLLECTIONS[name]


def _entity_filter(field: str, ids: list[str]) -> str:
    # Typesense nested-array filter syntax: parent.{child:=value}
    clean_ids = [_validate_id(item) for item in ids]
    if not clean_ids:
        return ""
    values = ", ".join(clean_ids)
    return f"{field}.{{id:=[{values}]}}"


def _build_filters(
    config: dict[str, Any],
    persons: list[str] | None,
    places: list[str] | None,
    organizations: list[str] | None,
    bibliographies: list[str] | None,
    date_from: int | None,
    date_to: int | None,
) -> list[str]:
    filters: list[str] = []
    requested = {
        "persons": persons or [],
        "places": places or [],
        "organizations": organizations or [],
        "bibliographies": bibliographies or [],
    }
    entity_fields = config.get("entity_fields", {})

    for category, ids in requested.items():
        if not ids:
            continue
        if category not in entity_fields:
            raise ValueError(
                f"{category!r} filtering is not configured for this collection"
            )
        filters.append(_entity_filter(entity_fields[category], ids))

    date_field = config.get("date_field")
    if date_from is not None or date_to is not None:
        if not date_field:
            raise ValueError("Date filtering is not configured for this collection")
        if date_from is not None and date_to is not None:
            if date_from > date_to:
                raise ValueError("date_from must be less than or equal to date_to")
            filters.append(f"{date_field}:[{date_from}..{date_to}]")
        elif date_from is not None:
            filters.append(f"{date_field}:>={date_from}")
        else:
            filters.append(f"{date_field}:<={date_to}")
    return filters


def _facet_payload(response: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for facet in response.get("facet_counts", []):
        field = facet.get("field_name", "unknown")
        values = []
        for item in facet.get("counts", []):
            row = {"value": item.get("value"), "count": item.get("count")}
            # With facet_return_parent Typesense includes the nested parent object.
            if item.get("highlighted"):
                row["highlighted"] = item["highlighted"]
            if item.get("parent"):
                row["parent"] = item["parent"]
            values.append(row)
        output[field] = {
            "counts": values,
            "stats": facet.get("stats", {}),
        }
    return output


@mcp.tool
def list_collections() -> dict[str, Any]:
    """List the Typesense collections enabled in this MCP server."""
    result = []
    for name, config in COLLECTIONS.items():
        result.append(
            {
                "name": name,
                "query_by": config["query_by"],
                "facets": config["default_facets"],
                "entity_filters": sorted(config["entity_fields"]),
                "date_filter": config.get("date_field"),
                "description": config.get("description", ""),
            }
        )
    return {"collections": result}


@mcp.tool
def search_documents(
    collection: str,
    query: str,
    persons: list[str] | None = None,
    places: list[str] | None = None,
    organizations: list[str] | None = None,
    bibliographies: list[str] | None = None,
    date_from: int | None = None,
    date_to: int | None = None,
    page: int = 1,
    per_page: int = 10,
    include_facets: bool = True,
) -> dict[str, Any]:
    """
    Search paragraph/document records in a configured Typesense collection.

    Entity arguments are lists of stable IDs (for example xml:id values), not names.
    Dates are inclusive integer bounds and work only when date_field is configured.
    """
    config = _collection(collection)
    if not query.strip():
        raise ValueError("query must not be empty; use '*' to browse with filters")
    if page < 1:
        raise ValueError("page must be >= 1")
    if not 1 <= per_page <= 100:
        raise ValueError("per_page must be between 1 and 100")

    filters = _build_filters(
        config, persons, places, organizations, bibliographies, date_from, date_to
    )
    facets = config["default_facets"] if include_facets else []
    params: dict[str, Any] = {
        "q": query,
        "query_by": ",".join(config["query_by"]),
        "page": page,
        "per_page": per_page,
        "facet_by": ",".join(facets) if facets else "",
        "max_facet_values": int(config.get("max_facet_values", 20)),
        "highlight_full_fields": ",".join(config["query_by"]),
    }
    if filters:
        params["filter_by"] = " && ".join(filters)
    if config.get("facet_return_parent"):
        params["facet_return_parent"] = ",".join(config["facet_return_parent"])
    if config.get("sort_by"):
        params["sort_by"] = config["sort_by"]
    if config.get("prefix") is not None:
        params["prefix"] = config["prefix"]

    response = client.collections[collection].documents.search(params)
    result_fields = config.get("result_fields") or None
    hits = []
    for hit in response.get("hits", []):
        document = hit.get("document", {})
        if result_fields:
            document = {
                key: value for key, value in document.items() if key in result_fields
            }
        hits.append(
            {
                "document": document,
                "highlights": hit.get("highlights", []),
                "text_match": hit.get("text_match"),
            }
        )

    return {
        "collection": collection,
        "query": query,
        "found": response.get("found", 0),
        "page": response.get("page", page),
        "out_of": response.get("out_of"),
        "hits": hits,
        "facets": _facet_payload(response),
    }


@mcp.tool
def get_search_facets(
    collection: str,
    query: str = "*",
    facet_fields: list[str] | None = None,
    persons: list[str] | None = None,
    places: list[str] | None = None,
    organizations: list[str] | None = None,
    bibliographies: list[str] | None = None,
    date_from: int | None = None,
    date_to: int | None = None,
    max_values: int = 50,
) -> dict[str, Any]:
    """
    Return facet values and counts for a query, optionally constrained by filters.
    facet_fields must be configured as default facets for this collection.
    """
    config = _collection(collection)
    available = config["default_facets"]
    selected = facet_fields or available
    invalid = set(selected) - set(available)
    if invalid:
        raise ValueError(f"Facets not configured for {collection}: {sorted(invalid)}")
    if not 1 <= max_values <= 250:
        raise ValueError("max_values must be between 1 and 250")

    filters = _build_filters(
        config, persons, places, organizations, bibliographies, date_from, date_to
    )
    params: dict[str, Any] = {
        "q": query or "*",
        "query_by": ",".join(config["query_by"]),
        "per_page": 0,
        "facet_by": ",".join(selected),
        "max_facet_values": max_values,
    }
    if filters:
        params["filter_by"] = " && ".join(filters)
    parents = config.get("facet_return_parent") or [
        field for field in selected if "." in field
    ]
    if parents:
        params["facet_return_parent"] = ",".join(parents)

    response = client.collections[collection].documents.search(params)
    return {
        "collection": collection,
        "query": query or "*",
        "found": response.get("found", 0),
        "facets": _facet_payload(response),
    }


@mcp.tool
def get_document(collection: str, document_id: str) -> dict[str, Any]:
    """Retrieve one indexed Typesense document by its Typesense document ID."""
    _collection(collection)
    try:
        document = client.collections[collection].documents[document_id].retrieve()
    except ObjectNotFound:
        return {"collection": collection, "id": document_id, "found": False}
    allowed = COLLECTIONS[collection].get("result_fields") or None
    if allowed:
        document = {key: value for key, value in document.items() if key in allowed}
    return {"collection": collection, "found": True, "document": document}


def main() -> None:
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8000"))
    path = os.environ.get("MCP_PATH", "/mcp")
    mcp.run(transport="http", host=host, port=port, path=path)


if __name__ == "__main__":
    main()
