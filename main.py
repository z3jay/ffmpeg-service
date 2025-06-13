from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse
import subprocess
import os
import tempfile
import shutil
import uuid
from pathlib import Path
import logging
from typing import Optional, List, Dict, Any
import json

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
            "/health": "GET - Health check",
            "/process-multi": "POST - Process multiple files with FFmpeg for complex operations"
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

@app.post("/process-multi")
async def process_multi_media(
    files: List[UploadFile] = File(...),
    operation: str = Form(...),
    command: Optional[str] = Form(default=None),
    output_format: Optional[str] = Form(default="mp4"),
    options: Optional[str] = Form(default=None)
):
    """
    Process multiple media files using FFmpeg for complex operations.
    
    Args:
        files: List of input media files
        operation: Type of operation ('concat', 'mix_audio', 'overlay', 'merge_av', 'custom')
        command: Custom FFmpeg command (for 'custom' operation)
        output_format: Output file extension (default: 'mp4')
        options: JSON string with operation-specific options
    
    Operations:
        - concat: Concatenate videos or audios
        - mix_audio: Mix multiple audio tracks
        - overlay: Overlay videos (picture-in-picture)
        - merge_av: Merge separate audio and video files
        - custom: Use custom FFmpeg command with multiple inputs
    
    Options examples:
        - concat: {"transition": "fade", "duration": 1.0}
        - mix_audio: {"normalize": true, "volumes": [1.0, 0.8, 0.6]}
        - overlay: {"positions": [{"x": 0, "y": 0}, {"x": 10, "y": 10}]}
        - merge_av: {"video_index": 0, "audio_index": 1}
    """
    
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="At least 2 files are required for multi-input operations")
    
    # Generate unique ID for this processing job
    job_id = str(uuid.uuid4())
    logger.info(f"Starting multi-input job {job_id} with operation: {operation}")
    
    # Create job-specific directories
    job_input_dir = INPUT_DIR / job_id
    job_output_dir = OUTPUT_DIR / job_id
    job_input_dir.mkdir(exist_ok=True)
    job_output_dir.mkdir(exist_ok=True)
    
    try:
        # Parse options if provided
        parsed_options = {}
        if options:
            try:
                parsed_options = json.loads(options)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid JSON in options parameter")
        
        # Save uploaded files
        input_paths = []
        for i, file in enumerate(files):
            filename = file.filename or f"input_{i}"
            input_path = job_input_dir / f"{i}_{filename}"
            
            with open(input_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            input_paths.append(str(input_path))
            logger.info(f"Job {job_id}: Saved input file {i}: {filename}")
        
        # Determine output filename
        output_filename = f"output.{output_format.lstrip('.')}"
        output_path = job_output_dir / output_filename
        
        # Build FFmpeg command based on operation
        ffmpeg_cmd = ["ffmpeg", "-y"]  # Overwrite output files
        
        if operation == "concat":
            ffmpeg_cmd.extend(_build_concat_command(input_paths, str(output_path), parsed_options))
        elif operation == "mix_audio":
            ffmpeg_cmd.extend(_build_mix_audio_command(input_paths, str(output_path), parsed_options))
        elif operation == "overlay":
            ffmpeg_cmd.extend(_build_overlay_command(input_paths, str(output_path), parsed_options))
        elif operation == "merge_av":
            ffmpeg_cmd.extend(_build_merge_av_command(input_paths, str(output_path), parsed_options))
        elif operation == "custom":
            if not command:
                raise HTTPException(status_code=400, detail="Custom operation requires a command parameter")
            ffmpeg_cmd.extend(_build_custom_command(input_paths, str(output_path), command))
        else:
            raise HTTPException(status_code=400, detail=f"Unknown operation: {operation}")
        
        logger.info(f"Job {job_id}: Running FFmpeg command: {' '.join(ffmpeg_cmd)}")
        
        # Execute FFmpeg command
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout for complex operations
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
        
        logger.info(f"Job {job_id}: Multi-input processing completed successfully")
        
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
        logger.error(f"Job {job_id}: Error processing files: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing files: {str(e)}")
    
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

def _build_concat_command(input_paths: List[str], output_path: str, options: Dict[str, Any]) -> List[str]:
    """Build FFmpeg command for concatenating videos/audios."""
    cmd = []
    
    # Add all input files
    for path in input_paths:
        cmd.extend(["-i", path])
    
    # Check if we want transitions
    if options.get("transition") == "fade":
        # Create complex filter for fade transitions
        duration = options.get("duration", 1.0)
        filter_complex = []
        
        for i in range(len(input_paths)):
            if i == 0:
                filter_complex.append(f"[{i}:v]")
            else:
                prev_label = f"v{i-1}" if i > 1 else "0:v"
                fade_in = f"[{i}:v]fade=in:0:{int(duration*30)}[v{i}fade]"
                filter_complex.append(f"{fade_in}; [{prev_label}][v{i}fade]overlay[v{i}]")
        
        cmd.extend(["-filter_complex", "; ".join(filter_complex)])
    else:
        # Simple concatenation
        filter_complex = f"concat=n={len(input_paths)}:v=1:a=1[outv][outa]"
        cmd.extend(["-filter_complex", filter_complex, "-map", "[outv]", "-map", "[outa]"])
    
    cmd.append(output_path)
    return cmd

def _build_mix_audio_command(input_paths: List[str], output_path: str, options: Dict[str, Any]) -> List[str]:
    """Build FFmpeg command for mixing multiple audio tracks."""
    cmd = []
    
    # Add all input files
    for path in input_paths:
        cmd.extend(["-i", path])
    
    # Build filter for audio mixing
    volumes = options.get("volumes", [1.0] * len(input_paths))
    
    # Ensure we have volume for each input
    while len(volumes) < len(input_paths):
        volumes.append(1.0)
    
    # Create volume filters
    volume_filters = []
    for i, vol in enumerate(volumes[:len(input_paths)]):
        volume_filters.append(f"[{i}:a]volume={vol}[a{i}]")
    
    # Create mix filter
    mix_inputs = "".join([f"[a{i}]" for i in range(len(input_paths))])
    mix_filter = f"{mix_inputs}amix=inputs={len(input_paths)}:duration=longest"
    
    filter_complex = "; ".join(volume_filters) + "; " + mix_filter
    cmd.extend(["-filter_complex", filter_complex])
    
    # Normalize if requested
    if options.get("normalize", False):
        cmd.extend(["-af", "loudnorm"])
    
    cmd.append(output_path)
    return cmd

def _build_overlay_command(input_paths: List[str], output_path: str, options: Dict[str, Any]) -> List[str]:
    """Build FFmpeg command for overlaying videos (picture-in-picture)."""
    cmd = []
    
    # Add all input files
    for path in input_paths:
        cmd.extend(["-i", path])
    
    # Get positions for overlays
    positions = options.get("positions", [])
    
    # Start with the first video as base
    filter_parts = []
    current_output = "0:v"
    
    for i in range(1, len(input_paths)):
        pos = positions[i-1] if i-1 < len(positions) else {"x": 10, "y": 10}
        x = pos.get("x", 10)
        y = pos.get("y", 10)
        
        overlay_filter = f"[{current_output}][{i}:v]overlay={x}:{y}"
        if i < len(input_paths) - 1:
            overlay_filter += f"[tmp{i}]"
            current_output = f"tmp{i}"
        
        filter_parts.append(overlay_filter)
    
    filter_complex = "; ".join(filter_parts)
    cmd.extend(["-filter_complex", filter_complex])
    
    # Mix audio from all inputs
    if len(input_paths) > 1:
        audio_mix = f"amix=inputs={len(input_paths)}:duration=longest"
        cmd.extend(["-filter_complex", f"{filter_complex}; {audio_mix}"])
    
    cmd.append(output_path)
    return cmd

def _build_merge_av_command(input_paths: List[str], output_path: str, options: Dict[str, Any]) -> List[str]:
    """Build FFmpeg command for merging separate audio and video files."""
    cmd = []
    
    # Add all input files
    for path in input_paths:
        cmd.extend(["-i", path])
    
    # Get video and audio indices
    video_index = options.get("video_index", 0)
    audio_index = options.get("audio_index", 1)
    
    # Map video and audio
    cmd.extend([
        "-map", f"{video_index}:v",
        "-map", f"{audio_index}:a",
        "-c:v", "copy",  # Copy video without re-encoding
        "-c:a", "aac"    # Re-encode audio to AAC
    ])
    
    cmd.append(output_path)
    return cmd

def _build_custom_command(input_paths: List[str], output_path: str, command: str) -> List[str]:
    """Build custom FFmpeg command with multiple inputs."""
    cmd = []
    
    # Add all input files
    for path in input_paths:
        cmd.extend(["-i", path])
    
    # Add user's custom command
    if command.strip():
        cmd.extend(command.split())
    
    cmd.append(output_path)
    return cmd

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 