from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import FileResponse
import subprocess
import os
import tempfile
import shutil
import uuid
from pathlib import Path
import logging
from typing import Optional, List, Dict, Any, Union
import json
import re
import shlex
import threading
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def detect_streams(file_path: str) -> Dict[str, bool]:
    """
    Detect what types of streams (video, audio) are available in a media file.
    Returns a dict with 'has_video' and 'has_audio' keys.
    """
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_streams", "-print_format", "json", file_path],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            logger.warning(f"ffprobe failed for {file_path}: {result.stderr}")
            return {"has_video": True, "has_audio": True}  # Assume both to be safe
        
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        
        has_video = any(stream.get("codec_type") == "video" for stream in streams)
        has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
        
        logger.info(f"Stream detection for {file_path}: video={has_video}, audio={has_audio}")
        return {"has_video": has_video, "has_audio": has_audio}
        
    except Exception as e:
        logger.warning(f"Failed to detect streams for {file_path}: {str(e)}")
        return {"has_video": True, "has_audio": True}  # Assume both to be safe

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
            "/process": "POST - Process single or multiple files with FFmpeg commands",
            "/process-named": "POST - Process named files with custom FFmpeg commands",
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

@app.post("/process-named")
async def process_named_media(request: Request):
    """
    Process media files with custom names that can be referenced in FFmpeg commands.
    
    Form Fields:
        - Any number of file uploads with custom names (e.g., 'main_video', 'background_audio', 'overlay')
        - command (required): FFmpeg command using placeholders for file names
        - output_format (optional): Output file extension (default: 'mp4')
    
    Example command: "-i {main_video} -i {background_audio} -c:v copy -c:a aac -shortest"
    
    The placeholders {file_name} will be replaced with actual file paths.
    """
    
    # Generate unique ID for this processing job
    job_id = str(uuid.uuid4())
    logger.info(f"Starting named file job {job_id}")
    
    # Create job-specific directories
    job_input_dir = INPUT_DIR / job_id
    job_output_dir = OUTPUT_DIR / job_id
    job_input_dir.mkdir(exist_ok=True)
    job_output_dir.mkdir(exist_ok=True)
    
    try:
        # Parse form data
        form_data = await request.form()
        
        # Extract command and options
        command = form_data.get("command")
        output_format = form_data.get("output_format", "mp4")
        
        if not command:
            raise HTTPException(
                status_code=400,
                detail="'command' parameter is required"
            )
        
        # Find all file uploads and non-file parameters
        uploaded_files = {}
        file_paths = {}
        
        for field_name, field_value in form_data.items():
            if hasattr(field_value, 'filename'):  # It's a file upload
                # Save the uploaded file
                filename = field_value.filename or f"{field_name}"
                input_path = job_input_dir / f"{field_name}_{filename}"
                
                with open(input_path, "wb") as buffer:
                    content = await field_value.read()
                    buffer.write(content)
                
                uploaded_files[field_name] = {
                    'path': str(input_path),
                    'filename': filename,
                    'size': len(content)
                }
                file_paths[field_name] = str(input_path)
                
                logger.info(f"Job {job_id}: Saved file '{field_name}': {filename} -> {input_path}")
                
                # Verify the file actually exists
                if not input_path.exists():
                    logger.error(f"Job {job_id}: File was not saved correctly: {input_path}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to save file {field_name}"
                    )
        
        if not uploaded_files:
            raise HTTPException(
                status_code=400,
                detail="At least one file upload is required"
            )
        
        # Determine output filename and format
        output_filename = f"output.{output_format.lstrip('.')}"
        output_path = job_output_dir / output_filename
        
        # Detect stream types in the first uploaded file to determine processing strategy
        first_file_path = list(file_paths.values())[0]
        stream_info = detect_streams(first_file_path)
        logger.info(f"Job {job_id}: Stream detection for first file: {stream_info}")
        
        # Build FFmpeg command by replacing placeholders
        ffmpeg_cmd = ["ffmpeg", "-y"]  # Overwrite output files
        
        # Replace placeholders in command with actual file paths
        processed_command = command
        logger.info(f"Job {job_id}: Original command: {command}")
        logger.info(f"Job {job_id}: Available file paths: {file_paths}")
        
        # Smart command adjustment for concat operations
        if "concat=n=" in processed_command and ":v=1:a=1" in processed_command:
            if not stream_info["has_audio"]:
                logger.info(f"Job {job_id}: No audio streams detected, adjusting concat filter to video-only")
                # Replace audio parameters in concat filter
                processed_command = processed_command.replace(":v=1:a=1[outv][outa]", ":v=1:a=0[outv]")
                # Remove audio mapping
                processed_command = processed_command.replace('-map "[outv]" -map "[outa]"', '-map "[outv]"')
                # Remove audio codec specification
                processed_command = processed_command.replace(" -c:a aac", "")
                processed_command = processed_command.replace(" -c:a", "")
                logger.info(f"Job {job_id}: Adjusted command for video-only: {processed_command}")
        
        # Handle xfade filter for video-only files
        if "xfade=" in processed_command and not stream_info["has_audio"]:
            if "acrossfade" in processed_command:
                logger.info(f"Job {job_id}: Removing audio crossfade for video-only files")
                # Remove the audio crossfade part and simplify to video-only
                # Convert xfade command to simple concat for video-only
                if "[0:v][1:v]xfade=" in processed_command:
                    processed_command = processed_command.replace(
                        '"[0:v][1:v]xfade=transition=fade:duration=1:offset=5[v];[0:a][1:a]acrossfade=d=1[a]" -map "[v]" -map "[a]"',
                        '"concat=n=2:v=1:a=0[outv]" -map "[outv]"'
                    )
                    logger.info(f"Job {job_id}: Converted xfade to concat for video-only: {processed_command}")
        
        for file_name, file_path in file_paths.items():
            placeholder = f"{{{file_name}}}"
            if placeholder in processed_command:
                processed_command = processed_command.replace(placeholder, f'"{file_path}"')
                logger.info(f"Job {job_id}: Replaced {placeholder} with {file_path}")
            else:
                logger.warning(f"Job {job_id}: Placeholder {placeholder} not found in command")
        
        logger.info(f"Job {job_id}: Processed command: {processed_command}")
        
        # Check if command contains input specifications
        if not processed_command.strip():
            raise HTTPException(
                status_code=400,
                detail="Command cannot be empty"
            )
        
        # Parse the processed command properly to handle quoted arguments
        try:
            parsed_args = shlex.split(processed_command)
            ffmpeg_cmd.extend(parsed_args)
        except ValueError as e:
            logger.error(f"Job {job_id}: Failed to parse command: {processed_command}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid command syntax: {str(e)}"
            )
        
        # Add output file
        ffmpeg_cmd.append(str(output_path))
        
        logger.info(f"Job {job_id}: Running FFmpeg command: {' '.join(ffmpeg_cmd)}")
        
        # Execute FFmpeg command
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=600
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
        
        logger.info(f"Job {job_id}: Named file processing completed successfully")
        
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
        logger.error(f"Job {job_id}: Error processing named files: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing named files: {str(e)}")
    
    finally:
        # Only cleanup input files immediately, leave output file for later cleanup
        try:
            if job_input_dir.exists():
                shutil.rmtree(job_input_dir)
            logger.info(f"Job {job_id}: Cleaned up input files")
        except Exception as e:
            logger.warning(f"Job {job_id}: Failed to cleanup input files: {str(e)}")
        
        # Schedule output cleanup after a delay to allow file serving to complete
        def delayed_cleanup():
            time.sleep(30)  # Wait 30 seconds before cleanup
            try:
                if job_output_dir.exists():
                    shutil.rmtree(job_output_dir)
                logger.info(f"Job {job_id}: Cleaned up output files (delayed)")
            except Exception as e:
                logger.warning(f"Job {job_id}: Failed to cleanup output files (delayed): {str(e)}")
        
        # Start cleanup in background thread
        cleanup_thread = threading.Thread(target=delayed_cleanup)
        cleanup_thread.daemon = True
        cleanup_thread.start()

@app.post("/process")
async def process_media(
    files: Union[UploadFile, List[UploadFile]] = File(...),
    command: Optional[str] = Form(default=None),
    operation: Optional[str] = Form(default=None),
    output_format: Optional[str] = Form(default=None),
    options: Optional[str] = Form(default=None)
):
    """
    Process single or multiple media files using FFmpeg.
    
    Single File Mode:
        - files: Single media file
        - command: FFmpeg command (without input/output paths)
        - output_format: Output file extension
    
    Multiple Files Mode:
        - files: List of media files (2+)
        - operation: Type of operation ('concat', 'mix_audio', 'overlay', 'merge_av', 'custom')
        - command: Custom FFmpeg command (required for 'custom' operation)
        - output_format: Output file extension (default: 'mp4')
        - options: JSON string with operation-specific options
    
    Multi-Input Operations:
        - concat: Concatenate videos or audios
        - mix_audio: Mix multiple audio tracks
        - overlay: Overlay videos (picture-in-picture)
        - merge_av: Merge separate audio and video files
        - custom: Use custom FFmpeg command with multiple inputs
    """
    
    # Handle both single file and multiple files input
    if isinstance(files, list):
        file_list = files
        is_multi_input = len(file_list) > 1
    else:
        file_list = [files]
        is_multi_input = False
    
    # Validate inputs
    if is_multi_input:
        if not operation:
            raise HTTPException(
                status_code=400, 
                detail="'operation' parameter is required for multiple files (concat, mix_audio, overlay, merge_av, custom)"
            )
        if operation == "custom" and not command:
            raise HTTPException(
                status_code=400, 
                detail="'command' parameter is required for custom multi-input operations"
            )
    else:
        if not command:
            raise HTTPException(
                status_code=400, 
                detail="'command' parameter is required for single file processing"
            )
    
    # Generate unique ID for this processing job
    job_id = str(uuid.uuid4())
    logger.info(f"Starting job {job_id} ({'multi-input' if is_multi_input else 'single'} mode)")
    
    # Create job-specific directories
    job_input_dir = INPUT_DIR / job_id
    job_output_dir = OUTPUT_DIR / job_id
    job_input_dir.mkdir(exist_ok=True)
    job_output_dir.mkdir(exist_ok=True)
    
    try:
        # Parse options if provided (for multi-input operations)
        parsed_options = {}
        if options:
            try:
                parsed_options = json.loads(options)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid JSON in options parameter")
        
        # Save uploaded files
        input_paths = []
        for i, file in enumerate(file_list):
            filename = file.filename or f"input_{i}"
            input_path = job_input_dir / (f"{i}_{filename}" if is_multi_input else filename)
            
            with open(input_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            input_paths.append(str(input_path))
            logger.info(f"Job {job_id}: Saved input file {i}: {filename}")
        
        # Determine output filename and format
        if output_format:
            output_filename = f"output.{output_format.lstrip('.')}"
        else:
            if is_multi_input:
                output_filename = "output.mp4"  # Default for multi-input
            else:
                # Use same extension as input file for single input
                input_ext = Path(file_list[0].filename or "input").suffix
                output_filename = f"output{input_ext}"
        
        output_path = job_output_dir / output_filename
        
        # Build FFmpeg command
        if is_multi_input:
            # Multi-input processing
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
                ffmpeg_cmd.extend(_build_custom_command(input_paths, str(output_path), command))
            else:
                raise HTTPException(status_code=400, detail=f"Unknown operation: {operation}")
        else:
            # Single file processing (original logic)
            ffmpeg_cmd = [
                "ffmpeg",
                "-y",  # Overwrite output files without asking
                "-i", input_paths[0],  # Input file
            ]
            
            # Add user's command
            if command.strip():
                ffmpeg_cmd.extend(command.split())
            
            # Add output file
            ffmpeg_cmd.append(str(output_path))
        
        logger.info(f"Job {job_id}: Running FFmpeg command: {' '.join(ffmpeg_cmd)}")
        
        # Execute FFmpeg command with appropriate timeout
        timeout = 600 if is_multi_input else 300  # 10 min for multi-input, 5 min for single
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=timeout
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
        logger.error(f"Job {job_id}: Error processing file(s): {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing file(s): {str(e)}")
    
    finally:
        # Only cleanup input files immediately, leave output file for later cleanup
        try:
            if job_input_dir.exists():
                shutil.rmtree(job_input_dir)
            logger.info(f"Job {job_id}: Cleaned up input files")
        except Exception as e:
            logger.warning(f"Job {job_id}: Failed to cleanup input files: {str(e)}")
        
        # Schedule output cleanup after a delay to allow file serving to complete
        def delayed_cleanup():
            time.sleep(30)  # Wait 30 seconds before cleanup
            try:
                if job_output_dir.exists():
                    shutil.rmtree(job_output_dir)
                logger.info(f"Job {job_id}: Cleaned up output files (delayed)")
            except Exception as e:
                logger.warning(f"Job {job_id}: Failed to cleanup output files (delayed): {str(e)}")
        
        # Start cleanup in background thread
        cleanup_thread = threading.Thread(target=delayed_cleanup)
        cleanup_thread.daemon = True
        cleanup_thread.start()

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