import os
import json
import concurrent.futures
import tempfile
from PIL import Image
import google.generativeai as genai
from gradio_client import Client, handle_file
import requests
from app.config import settings
from huggingface_hub import InferenceClient
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
    if isinstance(image_path, tuple):
        image_path = image_path[0]
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
            model="google/medgemma-4b-it",
            token=hf_token,
        )

        # Configuration for the quality assessment model (Gemini)
        self.quality_model = genai.GenerativeModel('gemini-2.5-flash')

    def _analyze_diagnosis_and_match(self, image_path: str, order_details: dict) -> dict:
        if not self.diagnostic_client:
            return {"error": "Diagnostic client not initialized."}

        system_prompt = """
        YOU ARE A RADIOLOGY AI. YOUR JOB IS TO ANALYZE A MEDICAL IMAGE AND RETURN A STRUCTURED REPORT BASED ON ITS CONTENT.

        User will provide:  
            - ordered_scan: {"scan_name": "...", "modality": "...", "age": "...", "sex": "..."}
            - scan_file: (image file)  

        TASKS:  
        1. Fetch scan_name from ordered_scan.  
        2. Compare actual vs expected:
        - If body_part shown in the image matches the scan_name then scan_match = True
        - Otherwise → scan_match = False  
        
        3.  **WRITE DIAGNOSIS**:
                    * Describe only what is visible in the image.
                    * Include descriptions of normal and any abnormal findings.
                    * Crucially, DO NOT mention the patient's age, sex, image quality, or clinical history in the diagnosis field.

        ## OUTPUT FORMAT (STRICT JSON):
        {
          "scan_name": "...",
          "age": "...",
          "sex": "...",
          "scan_match": True/False,
          "modality": "...",
          "diagnosis": "..."
        }

        """
        user_data_prompt = f"ordered_scan: {json.dumps(order_details)}"
        try:
            messages = [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_data_prompt},
                        {"type": "image_url", "image_url": {"url": image_path[0]}}
                    ]
                }
            ]         
            
            # The method returns a response object, not a string
            response_object = self.diagnostic_client.chat.completions.create(
                model="google/medgemma-4b-it",
                messages=messages,
                max_tokens=1024,
            )
            
            # --- FIX APPLIED HERE ---
            # Extract the string content from the response object
            result_str = response_object.choices[0].message.content
            
            # Now you can safely clean the response string to extract the JSON part
            json_part = result_str.split('```json\n')[-1].split('\n```')[0]
            return json.loads(json_part)

        except Exception as e:
            print(f"Error in diagnostic analysis: {e}")
            return {"error": f"Failed to get diagnostic analysis: {e}"}

    def _assess_image_quality(self, image_path: str, order_details : dict) -> dict:
        """
        Calls the Gemini model (API 2) to assess the image quality.

        Args:
            image_path: The local file path to the scan image.

        Returns:
            A dictionary with the quality assessment, or an error dict.
        """
        system_prompt = """
        YOU ARE AN AI SPECIALIZED IN MEDICAL IMAGE QUALITY ASSESSMENT.

        ## INPUT:
        - A MEDICAL SCAN IMAGE
        - NAME OF THE SCAN

        ## YOUR TASK:
        1.  **ANALYZE IMAGE QUALITY**: Carefully examine the image for clarity, artifacts, blur, and noise.
        2.  **ASSIGN QUALITY RATING**:
            * `"Optimal"`: The image is clear, sharp, with no artifacts or blur.
            * `"Sub-optimal"`: The image has minor issues (e.g., slight noise, small anatomical cut-offs, mild motion blur) but is still diagnostically useful.
            * `"Bad"`: The image is unreadable, has heavy artifacts, is severely blurred, or critical structures are missing, making it unsuitable for diagnosis.

        ## OUTPUT FORMAT (STRICT JSON):
        {
          "quality": "Optimal"
        }
        """
        try:
            img = Image.open(image_path)
            response = self.quality_model.generate_content([system_prompt, img],contents = order_details["scan_name"])
            
            # Clean the response to extract the JSON part
            json_part = response.text.strip().lstrip('```json').rstrip('```').strip()
            return json.loads(json_part)

        except Exception as e:
            print(f"Error in quality assessment: {e}")
            return {"error": f"Failed to get quality assessment: {e}"}

    def analyze_scan(self, image_path: str, order_details: dict) -> dict:
        """
        Performs a full analysis of a medical scan by running diagnostic and
        quality checks in parallel and combining the results.

        Args:
            image_path: The local file path or URL to the scan image.
            order_details: A dictionary with scan_name, modality, age, and sex.

        Returns:
            A consolidated JSON report with the final status.
        """
        local_image_path = _download_image_to_tempfile(image_path)
    
        if not local_image_path:
            # If the download fails, we cannot proceed.
            return {
                "status": "REJECTED",
                "reason": "Failed to download image from the provided URL for quality assessment.",
                "diagnosis_error": "Image download failed.",
                "quality_error": "Image download failed.",
            }

        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                # --- KEY CHANGE HERE ---
                # The diagnostic/Gradio function gets the original URL, as it requires.
                future_diagnosis = executor.submit(self._analyze_diagnosis_and_match, image_path, order_details)
                
                # The quality assessment function gets the temporary local file path to prevent errors.
                future_quality = executor.submit(self._assess_image_quality, local_image_path, order_details)

                # Retrieve results from both concurrent tasks
                diagnosis_result = future_diagnosis.result()
                quality_result = future_quality.result()

        finally:
            # Always clean up the temporary file after analysis is complete
            if os.path.exists(local_image_path):
                os.remove(local_image_path)

        # --- The rest of your result combination logic remains the same ---
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
            "status": "PENDING", # Will be updated below
            "quality": quality_result.get("quality", "Bad"),
            "scan_match": diagnosis_result.get("scan_match", False),
            "modality": order_details.get("modality", "Unknown"),
            "diagnosis": diagnosis_result.get("diagnosis", "No diagnosis could be generated.")
        }

        if not final_report["scan_match"] or final_report["quality"] == "Bad":
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

        # Example image path (using the bus image for demonstration purposes)
        # In a real scenario, this would be a medical scan image.
        # The model will likely fail the "scan_match" which demonstrates the rejection logic.
        image_file_path = 'https://raw.githubusercontent.com/gradio-app/gradio/main/test/test_files/bus.png'
        
        print(f"Image path: {image_file_path}\n")

        # Run the analysis
        analysis_result = llm_service.analyze_scan(image_file_path, order_details)

        # Print the final, consolidated report
        print("--- Final Analysis Report ---")
        print(json.dumps(analysis_result, indent=2))
        print("-----------------------------")

        # Example of a likely successful case (if you have a chest x-ray image)
        # try:
        #     chest_xray_path = "path/to/your/chest_xray.jpg"
        #     chest_order = {
        #         "scan_name": "Chest X-ray",
        #         "modality": "X-ray",
        #         "age": "62",
        #         "sex": "Female"
        #     }
        #     print("\nAnalyzing a chest x-ray (example):")
        #     chest_result = llm_service.analyze_scan(chest_xray_path, chest_order)
        #     print(json.dumps(chest_result, indent=2))
        # except FileNotFoundError:
        #      print("\nSkipping chest x-ray example: image file not found.")

