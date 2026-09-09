from app.extraction.evidence_workspace import WHOLE_SOURCE_CHARACTER_LIMIT, EvidenceWorkspace


def test_json_workspace_uses_document_paths_for_provenance_ready_chunks():
    workspace = EvidenceWorkspace.from_context(
        "json",
        {
            "source_json": {
                "offer": {"items": [{"product": "Panadol", "price": "1.20"}]},
            }
        },
    )

    assert workspace.mode == "whole_source"
    assert workspace.references() == ("json:$",)
    assert workspace.inspect(["json:$"])[0].metadata == {"path": "$"}
    assert workspace.has_reference("json:$.offer.items[0].price")


def test_pdf_workspace_keeps_each_page_intact_and_returns_related_search_results():
    workspace = EvidenceWorkspace.from_context(
        "pdf",
        {
            "pages": [
                {"page_number": 1, "text": "Product: Panadol\nUnit price: EUR 1.20"},
                {"page_number": 2, "text": "Shelf life: 24 months for all products."},
            ]
        },
    )

    matches = workspace.search("shelf life months")

    assert matches[0].reference == "pdf:page:2"
    assert matches[0].metadata["page_number"] == 2


def test_pdf_workspace_keeps_native_layout_addressable_without_reconstructing_it():
    workspace = EvidenceWorkspace.from_context(
        "pdf",
        {
            "pages": [
                {
                    "page_number": 1,
                    "text": "Panadol unit price",
                    "liteparse": {"tables": [{"headers": ["Product", "Price"]}]},
                }
            ]
        },
    )

    layout = workspace.inspect(["pdf:page:1"])

    assert layout[0].kind == "page"
    assert layout[0].metadata["atomic"] is True
    assert layout[0].metadata["has_native_layout"] is True
    assert '"Product"' in layout[0].text


def test_large_email_uses_chunked_retrieval_without_sending_full_source_by_default():
    text = "Panadol terms\n" * ((WHOLE_SOURCE_CHARACTER_LIMIT // len("Panadol terms\n")) + 1)
    workspace = EvidenceWorkspace.from_context("email", {"body_text": text})

    assert workspace.mode == "retrieval"
    assert len(workspace.chunks) > 1
    assert all(reference.startswith("email:body:") for reference in workspace.references())


def test_inspection_resolves_multiple_source_references_in_requested_order():
    workspace = EvidenceWorkspace.from_context(
        "email",
        {"body_text": "Initial price EUR 0.128\n\nCorrection price EUR 0.134"},
    )
    reference = workspace.references()[0]

    inspected = workspace.inspect(["missing", reference])

    assert [chunk.reference for chunk in inspected] == [reference]


def test_json_child_references_resolve_to_the_containing_chunk_for_scoped_search_and_inspection():
    workspace = EvidenceWorkspace.from_context(
        "json",
        {"source_json": {"offer": {"items": [{"name": "Panadol", "price": "1.20"}]}}},
    )

    matches = workspace.search("panadol", references=["json:$.offer.items[0].name"])
    inspected = workspace.inspect(["json:$.offer.items[0].name", "json:$.offer.items[0].price"])

    assert [chunk.reference for chunk in matches] == ["json:$"]
    assert [chunk.reference for chunk in inspected] == ["json:$"]
