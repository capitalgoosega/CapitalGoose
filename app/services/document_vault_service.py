import io
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import boto3
import requests
from botocore.client import Config
from sqlalchemy.orm import Session

from app.models.access_code import DocumentAccessGrant, generate_access_code

S3_BUCKET = os.environ["S3_BUCKET_NAME"]
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
PRESIGNED_URL_TTL_SECONDS = int(os.environ.get("PRESIGNED_URL_TTL_SECONDS", 900))
ACCESS_GRANT_TTL_DAYS = int(os.environ.get("ACCESS_GRANT_TTL_DAYS", 7))

_s3 = boto3.client(
  "s3",
  region_name=AWS_REGION,
  config=Config(signature_version="s3v4"),
)

def _document_prefix(application_id) -> str:
  return f"applications/{application_id}/documents/"


def ingest_document_from_url(application_id, source_url, filename=None) -> str:
  response = requests.get(source_url, timeout=30)
  response.raise_for_status()
  safe_name = filename or source_url.split("/")[-1].split("?")[0] or f"{uuid.uuid4()}.bin"
  key = f"{_document_prefix(application_id)}{safe_name}"
  _s3.upload_fileobj(
  io.BytesIO(response.content),
  S3_BUCKET,
  key,
  ExtraArgs={"ServerSideEncryption": "AES256"},
  )
  return key


def ingest_application_documents(application_id, document_urls: dict) -> list:
  return [
    ingest_document_from_url(application_id, url, filename=label)
    for label, url in document_urls.items()
  ]


def list_document_keys(application_id) -> list:
  paginator = _s3.get_paginator("list_objects_v2")
  keys = []
  for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=_document_prefix(application_id)):
    for obj in page.get("Contents", []):
      keys.append(obj["Key"])

  return keys



def generate_presigned_download_url(key: str) -> str:
  return _s3.generate_presigned_url(
    "get_object",
    Params={"Bucket": S3_BUCKET, "Key": key},
    ExpiresIn=PRESIGNED_URL_TTL_SECONDS,
  )


def create_access_grant(db: Session, application_id, recipient_email: str, recipient_label=None) -> DocumentAccessGrant:
  grant = DocumentAccessGrant(
    application_id=application_id,
    code=generate_access_code(),
    recipient_email=recipient_email,
    recipient_label=recipient_label,
    expires_at=DocumentAccessGrant.default_expiry(ACCESS_GRANT_TTL_DAYS),

  )
  db.add(grant)
  db.commit()
  db.refresh(grant)
  return grant


def validate_and_load_grant(db: Session, code: str):
  grant = db.query(DocumentAccessGrant).filter(DocumentAccessGrant.code == code).first()
  if not grant or grant.revoked:
    return None

  if grant.expires_at < datetime.now(timezone.utc):
    return None

  grant.access_count += 1
  grant.last_accessed_at = datetime.now(timezone.utc)
  db.commit()
  return grant


def revoke_grant(db: Session, code: str) -> bool:
  grant = db.query(DocumentAccessGrant).filter(DocumentAccessGrant.code == code).first()
  if not grant:
    return False

  grant.revoked = True
  db.commit()
  return True
