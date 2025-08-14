import os
import json
import concurrent.futures
import tempfile
from PIL import Image
import google.generativeai as genai
import requests
from app.config import settings
import time
from huggingface_hub import InferenceClient
import ast

# --- Configuration ---
# It's recommended to set your Gemini API key as an environment variable
# for security purposes.
GEMINI_API_KEY = settings.GEMINI_API_KEY
if not GEMINI_API_KEY:
    print("Warning: GEMINI_API_KEY environment variable not set.")
    # You can fallback to a hardcoded key for testing, but this is not recommended for production.
    # GEMINI_API_KEY = "YOUR_FALLBACK_API_KEY_HERE"

try:
    genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    print(f"Error configuring Gemini API: {e}")

def _download_image_to_tempfile(image_path: str) -> str:
    """
    Downloads an image from a URL and saves it to a temporary local file.
    This is necessary for any analysis function that cannot read from a URL directly.
    """
    try:
        response = requests.get(image_path, stream=True)
        response.raise_for_status()  # Raise an exception for bad status codes

        # Create a temporary file, ensuring it has a common image extension
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)
            return temp_file.name
    except requests.exceptions.RequestException as e:
        print(f"Error downloading image from {image_path}: {e}")
        return None

def _parse_image_paths(image_paths_str: str) -> list:
    """
    Parse the string representation of image paths list into actual list.
    Handles both string representation of list and actual list.
    """
    try:
        if isinstance(image_paths_str, str):
            # Try to parse as literal (for string representation of list)
            try:
                parsed = ast.literal_eval(image_paths_str)
                if isinstance(parsed, list):
                    return parsed
            except (ValueError, SyntaxError):
                # If literal_eval fails, try json.loads
                try:
                    parsed = json.loads(image_paths_str)
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    pass
            
            # If all parsing fails, treat as single URL
            return [image_paths_str]
        elif isinstance(image_paths_str, list):
            return image_paths_str
        else:
            return [str(image_paths_str)]
    except Exception as e:
        print(f"Error parsing image paths: {e}")
        return []
    
class MedicalLLMService:
    """
    A service to analyze medical scans by orchestrating two AI models:
    1. A Gradio-hosted model (medgemma-4b-it) for diagnosis and scan matching.
    2. A Gemini model for image quality assessment.

    The service runs these analyses in parallel, combines the results,
    and determines a final status for the scan.
    """

    def __init__(self):
        """Initializes the clients for the respective AI models."""
        hf_token = os.environ.get("HF_TOKEN")
        if not hf_token:
            raise ValueError("HF_TOKEN environment variable not set. Please provide your Hugging Face API key.")
            
        # Initialize the client to interact with the MedGemma model
        self.diagnostic_client = InferenceClient(
            provider="featherless-ai",
            token=hf_token,
        )

        # Configuration for the quality assessment model (Gemini)
        self.quality_model = genai.GenerativeModel('gemini-2.5-flash')

    def _analyze_diagnosis_and_match(self, image_paths: list, order_details: dict) -> dict:
        with open("app/services/MedgemmaPromptV5.txt",'r',encoding='utf-8') as f:
            system_prompt = f.read()
            
        user_data_prompt = f"ordered_scan: {json.dumps(order_details)}"
        try:
            # Prepare content with multiple images
            user_content = [{"type": "text", "text": user_data_prompt}]
            
            # Add all images to the content
            for image_path in image_paths:
                user_content.append({
                    "type": "image_url", 
                    "image_url": {"url": image_path}
                })
            
            messages = [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ]   
            payload = {
                    "input": {
                        "model": f"{settings.MODEL}",
                        "messages": messages,
                        "sampling_params":{"max_tokens": 4000}
                    }
                }      
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {settings.LLM_API}'
            }
            # The method returns a response object, not a string
            response_object = requests.post(settings.LLM_BASE_URL + 'run',headers=headers,json=payload)
            job_id = response_object.json()['id']
            """Poll RunPod for job completion"""
            
            headers = {
                'Authorization': f'Bearer {settings.LLM_API}'
            }
            
            while True:
                response = requests.get(settings.LLM_BASE_URL + f'status/{job_id}', headers=headers)
                result = response.json()
                
                status = result.get('status')
                
                if status == 'COMPLETED':
                    result_str = result.get('output')[0]['choices'][0]['tokens'][0]
                    json_part = result_str.split('```json\n')[-1].split('\n```')[0]
                    return json.loads(json_part)
                elif status == 'FAILED':
                    raise Exception(f"Job failed: {result}")
                elif status in ['IN_QUEUE', 'IN_PROGRESS']:
                    time.sleep(2)  # Wait 2 seconds before checking again
                else:
                    raise Exception(f"Unknown status: {status}")

        except Exception as e:
            print(f"Error in diagnostic analysis: {e}")
            return {"error": f"Failed to get diagnostic analysis: {e}"}

    def _assess_image_quality(self, local_image_paths: list, order_details: dict) -> dict:
        with open("app/services/SystemPromptV8.txt", "r",encoding='utf-8') as f:
            system_prompt = f.read()
        try:
            # Prepare content with all images
            content = [system_prompt]
            
            # Add all images to the content
            for image_path in local_image_paths:
                img = Image.open(image_path)
                content.append(img)
            
            # Add order details
            content.append(f"ordered_scan: {order_details}")
            
            response = self.quality_model.generate_content(content)
            
            # Clean the response to extract the JSON part
            json_part = response.text.strip().lstrip('```json').rstrip('```').strip()
            return json.loads(json_part)

        except Exception as e:
            print(f"Error in quality assessment: {e}")
            return {"error": f"Failed to get quality assessment: {e}"}

    def analyze_scan(self, image_paths_str: str, order_details: dict) -> dict:
        # Parse the image paths string into a list
        image_paths = _parse_image_paths(image_paths_str)
        
        if not image_paths:
            return {
                "status": "REJECTED",
                "reason": "No valid image paths provided.",
                "diagnosis_error": "No images to analyze.",
                "quality_error": "No images to analyze.",
            }
        
        # Download all images to temporary files
        local_image_paths = []
        failed_downloads = []
        
        for image_path in image_paths:
            local_path = _download_image_to_tempfile(image_path)
            if local_path:
                local_image_paths.append(local_path)
            else:
                failed_downloads.append(image_path)
        
        if not local_image_paths:
            # If all downloads failed, we cannot proceed
            return {
                "status": "REJECTED",
                "reason": "Failed to download any images from the provided URLs.",
                "diagnosis_error": "All image downloads failed.",
                "quality_error": "All image downloads failed.",
                "failed_downloads": failed_downloads,
            }

        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                # The diagnostic function gets the original URLs (multiple images)
                future_diagnosis = executor.submit(self._analyze_diagnosis_and_match, image_paths, order_details)
                
                # The quality assessment function gets the temporary local file paths
                future_quality = executor.submit(self._assess_image_quality, local_image_paths, order_details)

                # Retrieve results from both concurrent tasks
                diagnosis_result = future_diagnosis.result()
                quality_result = future_quality.result()

        finally:
            # Always clean up all temporary files after analysis is complete
            for local_path in local_image_paths:
                if os.path.exists(local_path):
                    os.remove(local_path)

        # Combine results
        if "error" in diagnosis_result or "error" in quality_result:
            return {
                "status": "REJECTED",
                "reason": "Failed to complete analysis due to API errors.",
                "diagnosis_error": diagnosis_result.get("error"),
                "quality_error": quality_result.get("error"),
            }
            
        final_report = {
            "scan_name": order_details.get("scan_name"),
            "age": order_details.get("age"),
            "sex": order_details.get("sex"),
            "modality": order_details.get("modality", "Unknown"),
            "quality": quality_result.get("image_quality", "rejected"),
            "scan_match": quality_result.get("scan_match", False),
            "modality_match":quality_result.get("modality_match",False),
            "reason_of_rejection":quality_result.get("reason_of_rejection","null"),
            "diagnosis": diagnosis_result.get("diagnosis", "No diagnosis could be generated."),
            "status": "PENDING", # Will be updated below
        }

        if not final_report["scan_match"] or not final_report["modality_match"] or final_report["quality"] == "rejected":
            final_report["status"] = "REJECTED"
        else:
            final_report["status"] = "ACCEPTED"

        return final_report
    
llm_service = MedicalLLMService()

# --- Example Usage ---
if __name__ == '__main__':
    # Ensure you have set the GEMINI_API_KEY environment variable before running
    if not GEMINI_API_KEY:
        print("\nERROR: Please set the 'GEMINI_API_KEY' environment variable to run this example.")
    else:
        # Create an instance of the service
        llm_service = MedicalLLMService()

        # Example order details
        order_details = {
            "scan_name": "CT Head",
            "modality": "CT",
            "age": "45",
            "sex": "Male"
        }

        # Example with multiple images (string representation of list)
        image_paths_str = '["https://raw.githubusercontent.com/gradio-app/gradio/main/test/test_files/bus.png", "https://raw.githubusercontent.com/gradio-app/gradio/main/test/test_files/bus.png"]'
        
        print(f"Image paths: {image_paths_str}\n")

        # Run the analysis
        analysis_result = llm_service.analyze_scan(image_paths_str, order_details)

        # Print the final, consolidated report
        print("--- Final Analysis Report ---")
        print(json.dumps(analysis_result, indent=2))
        print("-----------------------------")

        # Example with single image
        print("\nAnalyzing single image:")
        single_image_result = llm_service.analyze_scan(
            "https://raw.githubusercontent.com/gradio-app/gradio/main/test/test_files/bus.png", 
            order_details
        )
        print(json.dumps(single_image_result, indent=2))