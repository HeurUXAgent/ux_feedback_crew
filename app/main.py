from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uuid
import os
import json
from pathlib import Path
from src.ux_feedback_crew.crew_pipeline import (
    run_evaluation_pipeline,
    run_wireframe_pipeline
)


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

@app.post("/evaluate-ui/")
async def evaluate_ui(file: UploadFile = File(...)):
    try:
        # 1. Save upload
        job_id = str(uuid.uuid4())
        filename = f"{job_id}.png"
        upload_path = UPLOAD_DIR / filename

        with open(upload_path, "wb") as f:
            f.write(await file.read())

        # 2. Run Phase 1 Crew via the pipeline
        evaluation_result = run_evaluation_pipeline(str(upload_path))

        # 3. Save evaluation report as JSON for Phase 2 context
        output_path = OUTPUT_DIR / f"{job_id}_evaluation.json"
        with open(output_path, "w") as f:
            json.dump({"report": evaluation_result}, f, indent=2)

        return {
            "evaluation_id": job_id,
            "evaluation": evaluation_result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-wireframe/")
async def generate_wireframe(evaluation_id: str):
    try:
        evaluation_path = OUTPUT_DIR / f"{evaluation_id}_evaluation.json"
        
        if not evaluation_path.exists():
            raise HTTPException(status_code=404, detail="Evaluation not found")

        with open(evaluation_path) as f:
            evaluation_data = json.load(f)

        # 2. Run Phase 2 Crew
        # We pass the report from the JSON into the wireframe pipeline
        result = run_wireframe_pipeline(evaluation_data['report'])

        return {"wireframe_output": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))