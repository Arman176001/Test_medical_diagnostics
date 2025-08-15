import os
import base64
import json
import tempfile
import uuid
from google.cloud import storage
from google.oauth2 import service_account
from datetime import datetime, timedelta
from app.config import settings # Assuming you have a config file

class GCPStorageService:
    def __init__(self):
        """Initializes the GCP Storage client."""
        creds_b64 = os.environ.get('GCP_CREDENTIALS_BASE64')
        credentials = None

        if creds_b64:
            # Decode base64 service account for environments like Vercel/Heroku
            decoded_creds = base64.b64decode(creds_b64).decode('utf-8')
            creds_dict = json.loads(decoded_creds)
            credentials = service_account.Credentials.from_service_account_info(creds_dict)
        
        # Initialize client with credentials if available, otherwise use ADC
        self.client = storage.Client(
            project=settings.GCP_PROJECT_ID,
            credentials=credentials
        )
        self.bucket = self.client.bucket(settings.GCP_BUCKET_NAME)

    def generate_multiple_upload_urls(self, filenames: list[str], content_types: list[str]) -> list[dict]:
        """
        Generates signed URLs for uploading multiple files to a unique, shared folder.
        This is ideal for CT scan slices.
        """
        if not filenames or not content_types or len(filenames) != len(content_types):
            raise ValueError("Filenames and content_types lists must be non-empty and of equal length.")

        # Create a unique folder for this batch of uploads (e.g., a single CT scan)
        # The folder name is based on date and a unique ID
        scan_folder = f"uploads/{datetime.now().strftime('%Y/%m/%d')}/{uuid.uuid4()}"
        
        urls_data = []
        for i, filename in enumerate(filenames):
            # Sanitize filename to prevent directory traversal or other issues
            safe_filename = os.path.basename(filename)
            blob_name = f"{scan_folder}/{safe_filename}"
            blob = self.bucket.blob(blob_name)
            
            upload_url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(hours=1),
                method="PUT",
                content_type=content_types[i]
            )
            
            urls_data.append({
                "upload_url": upload_url,
                "blob_name": blob_name,
                "public_url": f"https://storage.googleapis.com/{self.bucket.name}/{blob_name}",
                "original_filename": filename,
                "content_type": content_types[i]
            })
            
        return urls_data

    def generate_upload_url(self, filename: str, content_type: str = 'application/octet-stream') -> dict:
        """
        DEPRECATED in favor of generate_multiple_upload_urls, but kept for single-file cases.
        Generate a signed URL for a single direct upload to the GCP bucket.
        """
        # For consistency, single uploads also go into a dated folder
        blob_name = f"uploads/{datetime.now().strftime('%Y/%m/%d')}/{uuid.uuid4()}-{os.path.basename(filename)}"
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
            "public_url": f"https://storage.googleapis.com/{self.bucket.name}/{blob_name}"
        }

    def get_image_url(self, blob_name: str) -> str:
        """Get public URL for an image."""
        return f"https://storage.googleapis.com/{self.bucket.name}/{blob_name}"

    def download_image(self, blob_name: str) -> bytes:
        """Download image as bytes for processing."""
        blob = self.bucket.blob(blob_name)
        return blob.download_as_bytes()

    def delete_image(self, blob_name: str):
        """Delete image from bucket."""
        blob = self.bucket.blob(blob_name)
        blob.delete()

# You would instantiate this service where needed
gcp_service = GCPStorageService()

# --- Example API Route (e.g., in FastAPI) ---
# @router.post("/generate-upload-urls")
# async def generate_upload_urls_endpoint(request: Request):
#     """
#     API endpoint to generate signed URLs for file uploads.
#     Accepts a JSON body with 'filenames' and 'content_types'.
#     """
#     try:
#         data = await request.json()
#         filenames = data.get("filenames")
#         content_types = data.get("content_types")
#
#         if not isinstance(filenames, list) or not isinstance(content_types, list):
#             raise HTTPException(status_code=400, detail="filenames and content_types must be arrays.")
#
#         response_data = gcp_service.generate_multiple_upload_urls(filenames, content_types)
#         return JSONResponse(content=response_data)
#
#     except Exception as e:
#         # Log the error e
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
