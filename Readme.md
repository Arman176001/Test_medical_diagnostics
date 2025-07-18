# Medical Testing App

A web application for uploading, processing, and analyzing medical scans using AI models. The app integrates with Supabase for database management, Google Cloud Storage for image uploads, and LLMs for automated scan analysis.

## Features

- Upload medical images (supports DICOM and standard image formats)
- Direct upload to Google Cloud Storage via signed URLs
- Automated scan analysis using LLMs (MedGemma, Gemini)
- Dashboard for viewing submissions and statistics
- Background processing of scans
- Results and recommendations for each scan

## Tech Stack

- **Backend:** FastAPI
- **Frontend:** Jinja2 templates (HTML/CSS/JS)
- **Database:** Supabase (PostgreSQL)
- **Cloud Storage:** Google Cloud Storage
- **AI Models:** Gradio Client (MedGemma), Google Generative AI (Gemini)
- **Containerization:** Docker

## Folder Structure

See [Structure.md](Structure.md) for a detailed breakdown.

## Setup

1. **Clone the repository**
   ```sh
   git clone <repo-url>
   cd medical_testing_app/app
   ```

2. **Install dependencies**
   ```sh
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   - Copy `.env.example` to `.env` and fill in your Supabase, GCP, and LLM credentials.

4. **Run the app (development)**
   ```sh
   uvicorn app.main:app --reload
   ```

5. **Run with Docker**
   ```sh
   docker build -t medical-testing-app .
   docker run -p 8000:8000 medical-testing-app
   ```

## Usage

- Visit `http://localhost:8000` to upload scans.
- Check processing status and results via the dashboard.
- API endpoints are available for integration.

## API Endpoints

- `POST /api/generate-upload-url` — Get signed URL for image upload
- `POST /api/submit-scan` — Submit scan metadata for processing
- `GET /api/result/{submission_id}` — Get scan result
- `GET /api/submissions` — List all submissions
- `GET /api/stats` — Get statistics

## License

MIT

## Authors

- Arman Chaudhary