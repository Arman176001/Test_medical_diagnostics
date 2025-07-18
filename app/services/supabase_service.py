import logging
from app.models.supabase_db import db
from typing import Dict, Any, Optional, List
import json

class SupabaseService:
    def __init__(self):
        self.db = db
    
    async def create_submission(self, scan_name: str, modality: str, age: int, 
                              sex: str, image_url: str, gcp_blob_name: str) -> Dict[str, Any]:
        """Create a new submission"""
        try:
            submission = self.db.create_submission(
                scan_name=scan_name,
                modality=modality,
                age=age,
                sex=sex,
                image_url=image_url,
                gcp_blob_name=gcp_blob_name
            )
            return submission
        except Exception as e:
            raise Exception(f"Error creating submission: {str(e)}")
    
    async def get_submission(self, submission_id: int) -> Optional[Dict[str, Any]]:
        """Get submission by ID"""
        try:
            return self.db.get_submission(submission_id)
        except Exception as e:
            raise Exception(f"Error retrieving submission: {str(e)}")
    
    async def update_submission_status(self, submission_id: int, status: str) -> bool:
        """Update submission status"""
        try:
            return self.db.update_submission_status(submission_id, status)
        except Exception as e:
            raise Exception(f"Error updating submission status: {str(e)}")
    
    async def save_result(self, submission_id: int, llm_result: Dict[str, Any],processing_time: float) -> Dict[str, Any]:

        try:
            # Pass the report values directly to the database creation method.
            # This assumes your 'create_result' method and table schema accept these arguments.
            result = self.db.create_result(
                submission_id=submission_id,
                patient_id=llm_result.get("patient_id"),
                scan_name=llm_result.get("scan_name"),
                image_path=llm_result.get("image_path"),
                age=llm_result.get("age"),
                sex=llm_result.get("sex"),
                status=llm_result.get("status"),
                quality=llm_result.get("quality"),
                scan_match=llm_result.get("scan_match"),
                modality=llm_result.get("modality"),
                diagnosis=llm_result.get("diagnosis"),
                processing_time=processing_time  # Assumes you have this column in your table
            )
            return result
        except Exception as e:
            logging.error(f"Failed to save result for submission {submission_id}. Error: {e}")
            raise Exception(f"Error saving result: {str(e)}")
    
    async def get_submission_with_result(self, submission_id: int) -> Optional[Dict[str, Any]]:
        """Get submission with its result"""
        try:
            return self.db.get_submission_with_result(submission_id)
        except Exception as e:
            raise Exception(f"Error retrieving submission with result: {str(e)}")
    
    async def get_all_submissions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all submissions"""
        try:
            return self.db.get_all_submissions(limit)
        except Exception as e:
            raise Exception(f"Error retrieving submissions: {str(e)}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get application statistics"""
        try:
            return self.db.get_stats()
        except Exception as e:
            raise Exception(f"Error retrieving stats: {str(e)}")

# Global instance
supabase_service = SupabaseService()