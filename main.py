from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse
import subprocess
import os
import tempfile
import shutil
import uuid
from pathlib import Path
import logging
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="FFmpeg Microservice API",
    description="A microservice for processing media files using FFmpeg commands",
    version="1.0.0"
)

# Create directories for temporary files
TEMP_DIR = Path("/tmp/ffmpeg_service")
TEMP_DIR.mkdir(exist_ok=True)
INPUT_DIR = TEMP_DIR / "input"
OUTPUT_DIR = TEMP_DIR / "output"
INPUT_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

@app.get("/")
async def root():
    return {
        "message": "FFmpeg Microservice API",
        "version": "1.0.0",
        "endpoints": {
            "/process": "POST - Process files with FFmpeg commands",
            "/health": "GET - Health check"
        }
    }

@app.get("/health")
async def health_check():
    try:
        # Check if FFmpeg is available
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
        ffmpeg_available = result.returncode == 0
        
        return {
            "status": "healthy" if ffmpeg_available else "unhealthy",
            "ffmpeg_available": ffmpeg_available,
            "ffmpeg_version": result.stdout.split('\n')[0] if ffmpeg_available else None
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "ffmpeg_available": False,
            "error": str(e)
        }

@app.post("/process")
async def process_media(
    file: UploadFile = File(...),
    command: str = Form(...),
    output_format: Optional[str] = Form(default=None)
):
    """
    Process a media file using FFmpeg command.
    
    Args:
        file: Input media file
        command: FFmpeg command (without input/output file paths)
        output_format: Output file extension (e.g., 'mp4', 'avi', 'wav')
    
    Example command: "-vf scale=640:480 -c:v libx264 -preset fast"
    """
    
    # Generate unique ID for this processing job
    job_id = str(uuid.uuid4())
    logger.info(f"Starting job {job_id}")
    
    # Create job-specific directories
    job_input_dir = INPUT_DIR / job_id
    job_output_dir = OUTPUT_DIR / job_id
    job_input_dir.mkdir(exist_ok=True)
    job_output_dir.mkdir(exist_ok=True)
    
    try:
        # Save uploaded file
        input_filename = file.filename or "input_file"
        input_path = job_input_dir / input_filename
        
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        logger.info(f"Job {job_id}: Saved input file {input_filename}")
        
        # Determine output filename and format
        if output_format:
            output_filename = f"output.{output_format.lstrip('.')}"
        else:
            # Use same extension as input file
            input_ext = Path(input_filename).suffix
            output_filename = f"output{input_ext}"
        
        output_path = job_output_dir / output_filename
        
        # Build FFmpeg command
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",  # Overwrite output files without asking
            "-i", str(input_path),  # Input file
        ]
        
        # Add user's command (split by spaces, but this is basic - might need more sophisticated parsing)
        if command.strip():
            ffmpeg_cmd.extend(command.split())
        
        # Add output file
        ffmpeg_cmd.append(str(output_path))
        
        logger.info(f"Job {job_id}: Running FFmpeg command: {' '.join(ffmpeg_cmd)}")
        
        # Execute FFmpeg command
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode != 0:
            logger.error(f"Job {job_id}: FFmpeg failed with return code {result.returncode}")
            logger.error(f"Job {job_id}: FFmpeg stderr: {result.stderr}")
            raise HTTPException(
                status_code=400,
                detail=f"FFmpeg processing failed: {result.stderr}"
            )
        
        # Check if output file was created
        if not output_path.exists():
            raise HTTPException(
                status_code=500,
                detail="Output file was not created"
            )
        
        logger.info(f"Job {job_id}: Processing completed successfully")
        
        # Return the processed file
        return FileResponse(
            path=str(output_path),
            filename=output_filename,
            media_type="application/octet-stream"
        )
        
    except subprocess.TimeoutExpired:
        logger.error(f"Job {job_id}: FFmpeg command timed out")
        raise HTTPException(status_code=408, detail="Processing timed out")
    
    except Exception as e:
        logger.error(f"Job {job_id}: Error processing file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
    
    finally:
        # Cleanup temporary files
        try:
            if job_input_dir.exists():
                shutil.rmtree(job_input_dir)
            if job_output_dir.exists():
                shutil.rmtree(job_output_dir)
            logger.info(f"Job {job_id}: Cleaned up temporary files")
        except Exception as e:
            logger.warning(f"Job {job_id}: Failed to cleanup temporary files: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 