"""
Rules for documents a partner uploads for a referral. Pure functions.

Uploads are raw bytes (PUT with a Content-Type), so the API needs no
multipart dependency. We trust the file's own header bytes, not the
Content-Type the client claims.
"""
import re

DOC_TYPES = {
    "bank_statement": "Bank statement",
    "tax_return": "Tax return",
    "government_id": "Government ID",
    "personal_financial_statement": "Personal Financial Statement",
    "other": "Other supporting document",
}
BASE_REQUIRED = ["bank_statement", "tax_return", "government_id"]
MAX_BYTES = 15 * 1024 * 1024
MAX_FILES_PER_REFERRAL = 20


def required_doc_types(pfs_required: bool):
    return BASE_REQUIRED + (["personal_financial_statement"] if pfs_required else [])


def missing_doc_types(present, required):
    have = set(present)
    return [t for t in required if t not in have]


def sniff_content_type(data: bytes):
    """Returns a MIME type for PDF/PNG/JPEG by magic bytes, else None."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def safe_filename(name: str, fallback: str = "document") -> str:
    """Strips paths and odd characters; keeps it short."""
    base = (name or "").replace("\\", "/").split("/")[-1]
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(" .")
    return (base or fallback)[:100]


def check_upload(data: bytes):
    """
    Shared by the partner API and the hosted widget.
    Returns (content_type, None, None) if OK, else (None, http_status, message).
    """
    if not data:
        return None, 422, "Empty file"
    if len(data) > MAX_BYTES:
        return None, 413, "File is larger than 15 MB"
    content_type = sniff_content_type(data)
    if not content_type:
        return None, 415, "Only PDF, PNG or JPEG files are accepted"
    return content_type, None, None
