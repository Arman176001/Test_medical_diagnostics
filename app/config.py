import os
from dotenv import load_dotenv
load_dotenv()

class Settings():
    # Supabase Database
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY')
    SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')
    
    # GCP Settings
    GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID')
    GCP_BUCKET_NAME = os.getenv('GCP_BUCKET_NAME')
    GCP_CREDENTIALS_PATH = os.getenv('GCP_CREDENTIALS_PATH')
    
    # LLM Settings
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    LLM_BASE_URL= "https://api.featherless.ai/v1"
    LLM_MODEL = "google/medgemma-4b-it"
    
    # App Settings
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key')
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    
    class Config:
        env_file = ".env"

settings = Settings()