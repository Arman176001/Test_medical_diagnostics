import os
import base64
import json
import tempfile
from google.cloud import storage
from google.oauth2 import service_account
from datetime import datetime, timedelta
from app.config import settings

class GCPStorageService:
    def __init__(self):
        # Priority: explicit file path > base64 env var > default credentials
        creds_path = settings.GCP_CREDENTIALS_PATH
        creds_b64 = os.environ.get('GCP_CREDENTIALS_BASE64')

        if creds_path:
            # Load from file path (local dev)
            credentials = service_account.Credentials.from_service_account_file(
                creds_path
            )
        elif creds_b64:
            # Decode base64 service account JSON (for Vercel deployment)
            decoded = base64.b64decode(creds_b64).decode('utf-8')
            creds_dict = json.loads(decoded)
            # Write to temporary file for SDK usage
            tf = tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.json')
            json.dump(creds_dict, tf)
            tf.flush()
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = tf.name
            credentials = service_account.Credentials.from_service_account_file(tf.name)
        else:
            # Fallback to ADC (e.g., on GCP environments)
            credentials = None

        # Initialize client with or without explicit credentials
        self.client = storage.Client(
            project=settings.GCP_PROJECT_ID,
            credentials=credentials
        )
        self.bucket = self.client.bucket(settings.GCP_BUCKET_NAME)

    def generate_upload_url(self, filename: str, content_type: str = 'image/png') -> dict:
        """Generate a signed URL for direct upload to GCP bucket"""
        blob_name = f"uploads/{datetime.now().strftime('%Y/%m/%d')}/{filename}"
        blob = self.bucket.blob(blob_name)
        upload_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=1),
            method="PUT",
            content_type=content_type
        )
        return {
            "upload_url": upload_url,
            "blob_name": blob_name,
            "public_url": f"https://storage.googleapis.com/{settings.GCP_BUCKET_NAME}/{blob_name}"
        }

    def get_image_url(self, blob_name: str) -> str:
        """Get public URL for an image"""
        return f"https://storage.googleapis.com/{settings.GCP_BUCKET_NAME}/{blob_name}"

    def download_image(self, blob_name: str) -> bytes:
        """Download image as bytes for processing"""
        blob = self.bucket.blob(blob_name)
        return blob.download_as_bytes()

    def delete_image(self, blob_name: str):
        """Delete image from bucket"""
        blob = self.bucket.blob(blob_name)
        blob.delete()

gcp_service = GCPStorageService()
