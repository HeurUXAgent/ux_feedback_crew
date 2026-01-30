from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uuid
import os
import json
from pathlib import Path
# Import from your pipeline bridge
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
        job_id = str(uuid.uuid4())
        upload_path = UPLOAD_DIR / f"{job_id}.png"

        with open(upload_path, "wb") as f:
            f.write(await file.read())

        # 1. Run Pipeline: Get BOTH the structured analysis and the feedback
        analysis_json, feedback_report = run_evaluation_pipeline(str(upload_path))

        # 2. Save BOTH so Phase 2 has the original layout map
        output_data = {
            "report": feedback_report,
            "original_analysis": analysis_json
        }
        
        output_path = OUTPUT_DIR / f"{job_id}_evaluation.json"
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)

        return {"evaluation_id": job_id, "evaluation": feedback_report}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-wireframe/")
async def generate_wireframe(evaluation_id: str):
    try:
        evaluation_path = OUTPUT_DIR / f"{evaluation_id}_evaluation.json"
        if not evaluation_path.exists():
            raise HTTPException(status_code=404, detail="Evaluation ID not found")

        with open(evaluation_path) as f:
            data = json.load(f)

        # 3. Pass both bits of data to keep the Dialog App identity
        result = run_wireframe_pipeline(
            data.get('report', ""), 
            data.get('original_analysis', "")
        )

        return {"wireframe_output": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline Error: {str(e)}")