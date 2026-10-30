"""
Personal Knowledge and RAG REST API Routes for TONY AI (Stage 11).
Provides endpoints for document ingestion, semantic & keyword search,
grounded question answering with citations, and document lifecycle management.
"""
import logging
from flask import Blueprint, current_app, jsonify, request

from knowledge.errors import (
    KnowledgeError,
    UnsupportedFileError,
    FileTooLargeError,
    DuplicateDocumentError,
    DocumentNotFoundError,
    KnowledgeSecurityError,
    CorruptedDocumentError
)

logger = logging.getLogger("tony.routes.knowledge")

knowledge_bp = Blueprint("knowledge", __name__, url_prefix="/api/knowledge")


def _get_knowledge_manager():
    """Retrieve KnowledgeManager instance from application context."""
    return current_app.config.get("KNOWLEDGE_MANAGER_INSTANCE")


@knowledge_bp.route("/ingest", methods=["POST"])
def ingest_document():
    """
    Ingest a document into the personal knowledge base.
    Accepts multipart/form-data file upload OR application/json with 'path'.
    """
    manager = _get_knowledge_manager()
    if not manager:
        return jsonify({"error": "Knowledge subsystem is not initialized."}), 500

    # 1. Handle multipart/form-data upload
    if "file" in request.files:
        f = request.files["file"]
        if not f or not f.filename:
            return jsonify({"error": "No file selected for upload."}), 400

        try:
            content = f.read()
            doc = manager.ingest_bytes(content_bytes=content, filename=f.filename)
            return jsonify({
                "message": f"Document '{doc.filename}' ingested and indexed successfully.",
                "document": doc.to_dict()
            }), 201
        except DuplicateDocumentError as de:
            return jsonify({"error": str(de), "duplicate": True}), 409
        except UnsupportedFileError as ue:
            return jsonify({"error": str(ue)}), 400
        except FileTooLargeError as fe:
            return jsonify({"error": str(fe)}), 413
        except KnowledgeSecurityError as se:
            return jsonify({"error": str(se)}), 403
        except CorruptedDocumentError as ce:
            return jsonify({"error": str(ce)}), 422
        except Exception as e:
            logger.error(f"Error in file ingestion: {e}")
            return jsonify({"error": str(e)}), 500

    # 2. Handle application/json with local path
    if request.is_json:
        data = request.get_json(silent=True) or {}
        path_str = data.get("path") or data.get("file_path")
        if not path_str:
            return jsonify({"error": "Field 'path' or uploaded 'file' is required."}), 400

        try:
            doc = manager.ingest_file(file_path=path_str)
            return jsonify({
                "message": f"Document '{doc.filename}' ingested and indexed successfully.",
                "document": doc.to_dict()
            }), 201
        except DuplicateDocumentError as de:
            return jsonify({"error": str(de), "duplicate": True}), 409
        except UnsupportedFileError as ue:
            return jsonify({"error": str(ue)}), 400
        except FileTooLargeError as fe:
            return jsonify({"error": str(fe)}), 413
        except KnowledgeSecurityError as se:
            return jsonify({"error": str(se)}), 403
        except CorruptedDocumentError as ce:
            return jsonify({"error": str(ce)}), 422
        except Exception as e:
            logger.error(f"Error in path ingestion: {e}")
            return jsonify({"error": str(e)}), 500

    return jsonify({"error": "Request must be multipart/form-data or application/json."}), 400


@knowledge_bp.route("/search", methods=["POST"])
def search_knowledge():
    """
    Search the personal knowledge base using hybrid fusion.
    Body: {"query": "...", "top_k": 5, "document_id": "...", "file_type": "..."}
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json(silent=True) or {}
    query = data.get("query")
    if not query or not isinstance(query, str) or not query.strip():
        return jsonify({"error": "A non-empty 'query' string is required."}), 400

    top_k = int(data.get("top_k", 5))
    doc_id = data.get("document_id")
    file_type = data.get("file_type")

    manager = _get_knowledge_manager()
    if not manager:
        return jsonify({"error": "Knowledge subsystem is not initialized."}), 500

    results = manager.search(query=query.strip(), top_k=top_k, document_id=doc_id, file_type=file_type)
    return jsonify({
        "query": query,
        "count": len(results),
        "results": [r.to_dict() for r in results]
    }), 200


@knowledge_bp.route("/ask", methods=["POST"])
def ask_knowledge():
    """
    Ask a question grounded in knowledge documents with source citations.
    Body: {"question": "...", "top_k": 5, "document_id": "..."}
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json(silent=True) or {}
    question = data.get("question") or data.get("query")
    if not question or not isinstance(question, str) or not question.strip():
        return jsonify({"error": "A non-empty 'question' string is required."}), 400

    top_k = int(data.get("top_k", 5))
    doc_id = data.get("document_id")

    manager = _get_knowledge_manager()
    if not manager:
        return jsonify({"error": "Knowledge subsystem is not initialized."}), 500

    ai_provider = current_app.config.get("AI_PROVIDER_INSTANCE")
    rag_res = manager.ask(question=question.strip(), top_k=top_k, document_id=doc_id, ai_provider=ai_provider)
    return jsonify(rag_res.to_dict()), 200


@knowledge_bp.route("/documents", methods=["GET"])
def list_documents():
    """List all indexed documents in the knowledge base."""
    manager = _get_knowledge_manager()
    if not manager:
        return jsonify({"error": "Knowledge subsystem is not initialized."}), 500

    docs = manager.list_documents()
    return jsonify({
        "documents": [d.to_dict() for d in docs],
        "count": len(docs)
    }), 200


@knowledge_bp.route("/documents/<document_id>", methods=["GET"])
def get_document_details(document_id: str):
    """Retrieve metadata and chunks of a specific document."""
    manager = _get_knowledge_manager()
    if not manager:
        return jsonify({"error": "Knowledge subsystem is not initialized."}), 500

    doc = manager.get_document(document_id)
    if not doc:
        return jsonify({"error": f"Document '{document_id}' not found."}), 404

    chunks = manager.db.get_chunks(document_id)
    doc_dict = doc.to_dict()
    doc_dict["chunks"] = [c.to_dict() for c in chunks]
    return jsonify({
        "status": "success",
        "document": doc_dict,
        **doc_dict
    }), 200


@knowledge_bp.route("/documents/<document_id>", methods=["DELETE"])
def delete_document(document_id: str):
    """Delete a document and its indexed chunks from the knowledge base."""
    manager = _get_knowledge_manager()
    if not manager:
        return jsonify({"error": "Knowledge subsystem is not initialized."}), 500

    try:
        success = manager.delete_document(document_id)
        return jsonify({
            "message": f"Document '{document_id}' deleted successfully.",
            "success": success
        }), 200
    except DocumentNotFoundError as de:
        return jsonify({"error": str(de)}), 404
    except Exception as e:
        logger.error(f"Error deleting document '{document_id}': {e}")
        return jsonify({"error": str(e)}), 500


@knowledge_bp.route("/documents/<document_id>/reindex", methods=["POST"])
def reindex_document(document_id: str):
    """Reindex an individual document."""
    manager = _get_knowledge_manager()
    if not manager:
        return jsonify({"error": "Knowledge subsystem is not initialized."}), 500

    try:
        doc = manager.reindex_document(document_id)
        return jsonify({
            "status": "success",
            "message": f"Document '{document_id}' reindexed successfully.",
            "document": doc.to_dict()
        }), 200
    except DocumentNotFoundError as de:
        return jsonify({"status": "error", "error": str(de)}), 404
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@knowledge_bp.route("/reindex", methods=["POST"])
def reindex_all_documents():
    """Reindex all indexed documents in the knowledge base, or single doc if document_id provided."""
    manager = _get_knowledge_manager()
    if not manager:
        return jsonify({"status": "error", "error": "Knowledge subsystem is not initialized."}), 500

    data = request.get_json(silent=True) or {}
    doc_id = data.get("document_id")
    if doc_id:
        try:
            doc = manager.reindex_document(doc_id)
            return jsonify({
                "status": "success",
                "message": f"Document '{doc_id}' reindexed successfully.",
                "document": doc.to_dict()
            }), 200
        except DocumentNotFoundError as de:
            return jsonify({"status": "error", "error": str(de)}), 404
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 500

    summary = manager.reindex_all()
    return jsonify({
        "status": "success",
        "message": f"Reindexed {summary['reindexed']} of {summary['total']} documents.",
        "summary": summary
    }), 200


@knowledge_bp.route("/stats", methods=["GET"])
def get_knowledge_stats():
    """Retrieve metrics and summary statistics for the personal knowledge base."""
    manager = _get_knowledge_manager()
    if not manager:
        return jsonify({"error": "Knowledge subsystem is not initialized."}), 500

    stats = manager.get_stats()
    return jsonify({
        "status": "success",
        "stats": stats,
        **stats
    }), 200


@knowledge_bp.route("/health", methods=["GET"])
def get_knowledge_health():
    """Check health and availability of storage and embedding components."""
    manager = _get_knowledge_manager()
    if not manager:
        return jsonify({"error": "Knowledge subsystem is not initialized."}), 500

    health = manager.check_health()
    return jsonify(health), 200
