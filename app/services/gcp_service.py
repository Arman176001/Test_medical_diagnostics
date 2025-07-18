from google.cloud import storage
from google.oauth2 import service_account
from datetime import datetime, timedelta
import os
from app.config import settings

class GCPStorageService:
    def __init__(self):
        if settings.GCP_CREDENTIALS_PATH:
            credentials = service_account.Credentials.from_service_account_file(
                settings.GCP_CREDENTIALS_PATH
            )
            self.client = storage.Client(
                project=settings.GCP_PROJECT_ID,
                credentials=credentials
            )
        else:
            # Use default credentials (for deployment)
            self.client = storage.Client(project=settings.GCP_PROJECT_ID)
        
        self.bucket = self.client.bucket(settings.GCP_BUCKET_NAME)
    
    def generate_upload_url(self, filename: str, content_type: str = 'image/png') -> dict:
        """Generate a signed URL for direct upload to GCP bucket"""
        blob_name = f"uploads/{datetime.now().strftime('%Y/%m/%d')}/{filename}"
        blob = self.bucket.blob(blob_name)
        
        # Generate signed URL valid for 1 hour
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