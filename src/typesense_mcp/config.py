TYPESENSE_COLLECTIONS_JSON = {
    "kalbeck-tagebuch-static": {
        "query_by": ["title", "full_text"],
        "default_facets": [
            "person_entities.id",
            "place_entities.id",
            "org_entities.id",
            "bibl_entities.id",
        ],
        "entity_fields": {
            "persons": "person_entities",
            "places": "place_entities",
            "organizations": "org_entities",
            "bibliographies": "bibl_entities",
        },
        "date_field": None,
        "result_fields": [
            "id",
            "rec_id",
            "paragraph_index",
            "page_index",
            "page_label",
            "title",
            "url",
            "full_text",
            "person_entities",
            "place_entities",
            "org_entities",
            "bibl_entities",
        ],
        "description": "Paragraph-level index of the Kalbeck diary, with searchable text and linked entities.",
    }
}
