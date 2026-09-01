from flask import Blueprint, g, jsonify, request

from ..text_service import text_service

texts_bp = Blueprint("texts", __name__, url_prefix="/api/texts")


@texts_bp.route("", methods=["GET"])
def list_texts():
    notes = text_service.list_notes(g.current_user["id"])
    return jsonify(notes)


@texts_bp.route("", methods=["POST"])
def add_text():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"detail": "invalid json"}), 400

    content = str(payload.get("content", "")).strip()
    if not content:
        return jsonify({"detail": "content is required"}), 400

    note_id = text_service.add_note(g.current_user["id"], content)
    return jsonify({"id": note_id}), 201


@texts_bp.route("/<int:note_id>", methods=["DELETE"])
def delete_text(note_id: int):
    deleted = text_service.delete_note(g.current_user["id"], note_id)
    if not deleted:
        return jsonify({"detail": "text not found"}), 404
    return "", 204
