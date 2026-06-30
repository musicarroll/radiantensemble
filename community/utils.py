import hashlib
import hmac
import json
import mimetypes

from django.conf import settings


def _seek_if_possible(file_obj, position):
    try:
        file_obj.seek(position)
    except (AttributeError, OSError):
        pass


def calculate_sha256(file_obj):
    """Stream a file-like object into SHA-256 without loading it into memory."""
    original_position = None
    try:
        original_position = file_obj.tell()
    except (AttributeError, OSError):
        pass

    _seek_if_possible(file_obj, 0)
    digest = hashlib.sha256()
    if hasattr(file_obj, "chunks"):
        for chunk in file_obj.chunks():
            digest.update(chunk)
    else:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)

    if original_position is not None:
        _seek_if_possible(file_obj, original_position)
    else:
        _seek_if_possible(file_obj, 0)
    return digest.hexdigest()


def detect_mime_type(file_obj, filename=""):
    original_position = None
    try:
        original_position = file_obj.tell()
    except (AttributeError, OSError):
        pass

    _seek_if_possible(file_obj, 0)
    sample = b""
    try:
        sample = file_obj.read(2048)
    except (AttributeError, OSError):
        pass

    if original_position is not None:
        _seek_if_possible(file_obj, original_position)
    else:
        _seek_if_possible(file_obj, 0)

    if sample:
        try:
            import magic

            detected = magic.from_buffer(sample, mime=True)
            if detected:
                return detected
        except (ImportError, AttributeError, OSError):
            pass

    guessed, _encoding = mimetypes.guess_type(filename)
    return guessed or ""


def _metadata_payload(*, original_filename, stored_filename, mime_type, file_size, sha256_checksum):
    return {
        "file_size": int(file_size or 0),
        "mime_type": mime_type or "",
        "original_filename": original_filename or "",
        "sha256_checksum": sha256_checksum or "",
        "stored_filename": stored_filename or "",
    }


def sign_artifact_metadata(
    *,
    original_filename,
    stored_filename,
    mime_type,
    file_size,
    sha256_checksum,
):
    payload = _metadata_payload(
        original_filename=original_filename,
        stored_filename=stored_filename,
        mime_type=mime_type,
        file_size=file_size,
        sha256_checksum=sha256_checksum,
    )
    message = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    key = settings.ARTIFACT_METADATA_HMAC_KEY.encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def verify_artifact_metadata_signature(artifact):
    if not artifact.metadata_signature:
        return False
    expected = sign_artifact_metadata(
        original_filename=artifact.original_filename,
        stored_filename=artifact.stored_filename,
        mime_type=artifact.mime_type,
        file_size=artifact.file_size,
        sha256_checksum=artifact.sha256_checksum,
    )
    return hmac.compare_digest(expected, artifact.metadata_signature)
