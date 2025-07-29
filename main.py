from fastapi import FastAPI, Request, Form, HTTPException, BackgroundTasks
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from app.services.gcp_service import gcp_service
from app.services.llm_service import llm_service
from app.services.supabase_service import supabase_service
import uuid
import time
from pydantic import BaseModel

class UploadURLRequest(BaseModel):
    filename: str
    content_type: str

        
app = FastAPI(title="Medical Testing App", version="1.0.0")

# Setup templates and static files
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def upload_form(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})

@app.post("/api/generate-upload-url")
async def generate_upload_url(request: UploadURLRequest): # Use the Pydantic model here
    """Generate signed URL for direct upload to GCP bucket"""
    try:
        # Access data from the request object
        unique_filename = f"{uuid.uuid4()}_{request.filename}"
        upload_data = gcp_service.generate_upload_url(unique_filename, request.content_type)

        return JSONResponse(content=upload_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/submit-scan")
async def submit_scan(
    background_tasks: BackgroundTasks,
    scan_name: str = Form(...),
    modality: str = Form(...),
    age: int = Form(...),
    sex: str = Form(...),
    image_url: str = Form(...),
    blob_name: str = Form(...)
):
    """Submit scan for processing"""
    try:
        # Create submission record in Supabase
        submission = await supabase_service.create_submission(
            scan_name=scan_name,
            modality=modality,
            age=age,
            sex=sex,
            image_url=image_url,
            gcp_blob_name=blob_name
        )
        
        # Start background processing
        background_tasks.add_task(process_scan, submission['id'])
        
        return JSONResponse(content={
            "submission_id": submission['id'],
            "status": "submitted",
            "message": "Scan submitted for processing"
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def process_scan(submission_id: int):
    """Background task to process scan"""
    try:
        # Get submission
        submission = await supabase_service.get_submission(submission_id)
        if not submission:
            return
        
        # Update status to processing
        await supabase_service.update_submission_status(submission_id, "processing")
        
        # Process with LLM
        order_details = {
            "scan_name": submission['scan_name'],
            "modality": submission['modality'],
            "age": submission['age'],
            "sex": submission['sex']
        }

        # Measure the processing time for the analysis
        start_time = time.time()
        image_path=submission['image_url']
        # Call the function with the correct arguments
        llm_result = llm_service.analyze_scan(
            image_path=image_path,
            order_details=order_details
        )

        processing_time = time.time() - start_time
        
        # Save result
        await supabase_service.save_result(submission_id, image_path, llm_result, processing_time)
        
        # Update submission status
        await supabase_service.update_submission_status(submission_id, "completed")
        
    except Exception as e:
        # Update status to failed
        await supabase_service.update_submission_status(submission_id, "failed")
        print(f"Error processing scan {submission_id}: {str(e)}")

@app.get("/api/result/{submission_id}")
async def get_result(submission_id: int):
    """Get processing result with updated fields"""
    try:
        # Assume supabase_service.get_submission_with_result fetches submission and its related result
        data = await supabase_service.get_submission_with_result(submission_id)
        if not data:
            raise HTTPException(status_code=404, detail="Submission not found")
        
        response_data = {
            "submission_id": data.get('id'),
            "status": data.get('status'),
            "scan_name": data.get('scan_name'),
            "modality": data.get('modality'),
            "age": data.get('age'),
            "sex": data.get('sex'),
            "image_url": data.get('image_url'),
            "created_at": data.get('created_at')
        }

        if data.get('results') and len(data['results']) > 0:
            result = data['results'][0]
            
            response_data.update({
                "status": result.get('status'),
                "quality": result.get('quality'),
                "scan_match": result.get('scan_match'),
                "modality_match": result.get('modality_match'), 
                "reason_of_rejection": result.get('reason_of_rejection'), 
                "diagnosis": result.get('diagnosis'),
                "processing_time": result.get('processing_time')
            })
        
        return JSONResponse(content=response_data)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

@app.get("/api/submissions")
async def get_submissions(limit: int = 100):
    """Get all submissions"""
    try:
        submissions = await supabase_service.get_all_submissions(limit)
        return JSONResponse(content=submissions)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats")
async def get_stats():
    """Get application statistics"""
    try:
        stats = await supabase_service.get_stats()
        return JSONResponse(content=stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/results/{submission_id}", response_class=HTMLResponse)
async def result_page(request: Request, submission_id: int):
    return templates.TemplateResponse("results.html", {
        "request": request,
        "submission_id": submission_id
    })

@app.get("/processing/{submission_id}", response_class=HTMLResponse)
async def processing_page(request: Request, submission_id: int):
    return templates.TemplateResponse("processing.html", {
        "request": request,
        "submission_id": submission_id
    })

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)