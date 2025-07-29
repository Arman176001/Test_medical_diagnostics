from supabase import create_client, Client
from app.config import settings
from datetime import datetime
from typing import Optional, Dict, Any, List

class SupabaseDB:
    def __init__(self):
        self.client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    
    def create_tables(self):
        """Create tables if they don't exist"""
        # Create submissions table
        submissions_sql = """
        CREATE TABLE IF NOT EXISTS submissions (
            id SERIAL PRIMARY KEY,
            scan_name VARCHAR(255) NOT NULL,
            modality VARCHAR(50) NOT NULL,
            age INTEGER NOT NULL,
            sex VARCHAR(10) NOT NULL,
            image_url VARCHAR(500) NOT NULL,
            gcp_blob_name VARCHAR(500) NOT NULL,
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        """
        
        # Create results table
        results_sql = """
        CREATE TABLE IF NOT EXISTS results (
            -- Core Fields
            id SERIAL PRIMARY KEY,
            submission_id INTEGER REFERENCES submissions(id) ON DELETE CASCADE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

            -- Patient and Scan Details from the Report
            scan_name TEXT,
            image_path TEXT,
            age INTEGER,
            sex VARCHAR(50),
            modality VARCHAR(100),

            -- Analysis Outcome
            status VARCHAR(50) NOT NULL, -- e.g., 'ACCEPTED', 'REJECTED'
            quality VARCHAR(50),         -- e.g., 'Good', 'Bad'
            scan_match BOOLEAN,
            diagnosis TEXT,

            -- Performance Metrics
            processing_time REAL
        );

        """
        
        # Execute SQL (Note: This is for initial setup - in production, use Supabase dashboard)
        try:
            self.client.rpc('exec_sql', {'sql': submissions_sql})
            self.client.rpc('exec_sql', {'sql': results_sql})
        except Exception as e:
            print(f"Table creation error (may already exist): {e}")
    
    # Submission operations
    def create_submission(self, scan_name: str, modality: str, age: int, sex: str, 
                         image_url: str, gcp_blob_name: str) -> Dict[str, Any]:
        """Create a new submission"""
        data = {
            'scan_name': scan_name,
            'modality': modality,
            'age': age,
            'sex': sex,
            'image_url': image_url,
            'gcp_blob_name': gcp_blob_name,
            'status': 'pending'
        }
        
        result = self.client.table('submissions').insert(data).execute()
        return result.data[0] if result.data else None
    
    def get_submission(self, submission_id: int) -> Optional[Dict[str, Any]]:
        """Get submission by ID"""
        result = self.client.table('submissions').select('*').eq('id', submission_id).execute()
        return result.data[0] if result.data else None
    
    def update_submission_status(self, submission_id: int, status: str) -> bool:
        """Update submission status"""
        result = self.client.table('submissions').update({
            'status': status,
            'updated_at': datetime.now().isoformat()
        }).eq('id', submission_id).execute()
        return len(result.data) > 0
    
    def get_all_submissions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all submissions with pagination"""
        result = self.client.table('submissions').select('*').order('created_at', desc=True).limit(limit).execute()
        return result.data
    
    # Result operations
    def create_result(self, submission_id: int, scan_name: str, image_path: str, age: int, sex: str,modality:str, quality: str, scan_match: bool, modality_match: bool,reason_of_rejection:str, diagnosis: str,status: str, processing_time: float) -> Dict[str, Any]:

        data = {
            'submission_id': submission_id,
            'scan_name': scan_name,
            'image_path': image_path,
            'age': age,
            'sex': sex,
            'modality': modality,
            'quality': quality,
            'scan_match': scan_match,
            'modality_match': modality_match,
            'reason_of_rejection': reason_of_rejection,
            'diagnosis': diagnosis,
            'status': status,
            'processing_time': processing_time
        }
        
        try:
            # The insert operation remains the same, but the data payload is now correct.
            result = self.client.table('results').insert(data).execute()
            
            # Also, update the status of the original submission to reflect completion.
            self.client.table('submissions').update({'status': status}).eq('id', submission_id).execute()

            return result.data[0] if result.data else None
        except Exception as e:
            # It's good practice to log the error.
            print(f"Error creating result for submission {submission_id}: {e}")
            return None
    
    def get_result_by_submission(self, submission_id: int) -> Optional[Dict[str, Any]]:
        """Get result by submission ID"""
        result = self.client.table('results').select('*').eq('submission_id', submission_id).execute()
        return result.data[0] if result.data else None
    
    def get_submission_with_result(self, submission_id: int) -> Optional[Dict[str, Any]]:
        """Get submission with its result using a join"""
        result = self.client.table('submissions').select(
            '*, results(*)'
        ).eq('id', submission_id).execute()
        return result.data[0] if result.data else None
    
    # Analytics and reporting
    def get_stats(self) -> Dict[str, Any]:
        """Get basic statistics"""
        # Count total submissions
        total_submissions = self.client.table('submissions').select('id', count='exact').execute()
        
        # Count by status
        pending = self.client.table('submissions').select('id', count='exact').eq('status', 'pending').execute()
        completed = self.client.table('submissions').select('id', count='exact').eq('status', 'completed').execute()
        failed = self.client.table('submissions').select('id', count='exact').eq('status', 'failed').execute()
        
        # Count by decision
        accepted = self.client.table('results').select('id', count='exact').eq('decision', 'accepted').execute()
        rejected = self.client.table('results').select('id', count='exact').eq('decision', 'rejected').execute()
        
        return {
            'total_submissions': total_submissions.count,
            'pending': pending.count,
            'completed': completed.count,
            'failed': failed.count,
            'accepted': accepted.count,
            'rejected': rejected.count
        }

# Global instance
db = SupabaseDB()