from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import uuid
import os
import json
from pathlib import Path
import shutil
# Import from your pipeline bridge
from src.ux_feedback_crew.crew_pipeline import run_full_ux_pipeline
# (
#     run_evaluation_pipeline,
#     run_wireframe_pipeline
# )
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def cleanup_files(*paths: Path):
    """Deletes files after the response is sent."""
    for path in paths:
        try:
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
            print(f"Successfully cleaned up: {path}")
        except Exception as e:
            print(f"Cleanup error: {e}")

@app.post("/analyze-and-wireframe/")
async def analyze_and_wireframe(background_tasks: BackgroundTasks,file: UploadFile = File(...)):
    try:
        # 1. Save the Dialog app screenshot
        job_id = str(uuid.uuid4())
        upload_path = UPLOAD_DIR / f"{job_id}.png"

        with open(upload_path, "wb") as f:
            f.write(await file.read())

        # 2. Run the Consolidated Pipeline (All 4 Agents)
        # This returns the report and the wireframe in one execution
        feedback_report, wireframe_output = run_full_ux_pipeline(str(upload_path))

        # 3. Save everything to a single JSON for records
        final_data = {
            "evaluation_id": job_id,
            "feedback": feedback_report,
            "wireframe": wireframe_output
        }
        
        job_id = str(uuid.uuid4())
        upload_path = UPLOAD_DIR / f"{job_id}.png"
        result_json_path = OUTPUT_DIR / f"{job_id}_result.json"

        with open(result_json_path, "w") as f:
            json.dump(final_data, f, indent=2)

        background_tasks.add_task(cleanup_files, upload_path, result_json_path)

        # 4. Return everything to Flutter in one response
        return final_data
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"System Error: {str(e)}")
