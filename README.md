# FFmpeg Microservice API

A Docker-based microservice API for processing media files using FFmpeg commands.

## Features

- **RESTful API**: FastAPI-based service with automatic documentation
- **Single File Processing**: Accept media files via multipart/form-data
- **Multi-Input Operations**: Combine multiple videos and audios with complex operations
- **Custom FFmpeg Commands**: Execute any FFmpeg command on uploaded files
- **File Download**: Return processed files directly through the API
- **Health Monitoring**: Built-in health check endpoint
- **Automatic Cleanup**: Temporary files are automatically cleaned up after processing

## Quick Start

### Using Docker Compose (Recommended)

1. Clone or download this repository
2. Build and start the service:
   ```bash
   docker-compose up --build
   ```

### Using Docker

1. Build the image:
   ```bash
   docker build -t ffmpeg-service .
   ```

2. Run the container:
   ```bash
   docker run -p 8000:8000 ffmpeg-service
   ```

## API Endpoints

### Health Check
- **GET** `/health` - Check service health and FFmpeg availability

### Process Single Media File
- **POST** `/process` - Process a media file with FFmpeg

#### Parameters:
- `file` (required): Media file to process
- `command` (required): FFmpeg command (without input/output paths)
- `output_format` (optional): Output file extension (e.g., 'mp4', 'avi', 'wav')

### Process Multiple Media Files
- **POST** `/process-multi` - Process multiple media files with complex operations

#### Parameters:
- `files` (required): List of media files to process
- `operation` (required): Type of operation ('concat', 'mix_audio', 'overlay', 'merge_av', 'custom')
- `command` (optional): Custom FFmpeg command (required for 'custom' operation)
- `output_format` (optional): Output file extension (default: 'mp4')
- `options` (optional): JSON string with operation-specific options

#### Supported Operations:
- **concat**: Concatenate videos or audios sequentially
- **mix_audio**: Mix multiple audio tracks together
- **overlay**: Overlay videos (picture-in-picture effect)
- **merge_av**: Merge separate audio and video files
- **custom**: Use custom FFmpeg command with multiple inputs

## Usage Examples

### Example 1: Convert Video to Different Format
```bash
curl -X POST "http://localhost:8000/process" \
  -F "file=@input.mov" \
  -F "command=-c:v libx264 -preset fast -crf 23" \
  -F "output_format=mp4" \
  --output converted.mp4
```

### Example 2: Resize Video
```bash
curl -X POST "http://localhost:8000/process" \
  -F "file=@large_video.mp4" \
  -F "command=-vf scale=640:480 -c:v libx264 -preset fast" \
  --output resized_video.mp4
```

### Example 3: Extract Audio from Video
```bash
curl -X POST "http://localhost:8000/process" \
  -F "file=@video.mp4" \
  -F "command=-vn -acodec copy" \
  -F "output_format=aac" \
  --output audio.aac
```

### Example 4: Convert Audio Format
```bash
curl -X POST "http://localhost:8000/process" \
  -F "file=@audio.wav" \
  -F "command=-acodec mp3 -ab 192k" \
  -F "output_format=mp3" \
  --output converted_audio.mp3
```

### Example 5: Create Video Thumbnail
```bash
curl -X POST "http://localhost:8000/process" \
  -F "file=@video.mp4" \
  -F "command=-ss 00:00:01 -vframes 1" \
  -F "output_format=jpg" \
  --output thumbnail.jpg
```

## Multi-Input Usage Examples

### Example 1: Concatenate Multiple Videos
```bash
curl -X POST "http://localhost:8000/process-multi" \
  -F "files=@video1.mp4" \
  -F "files=@video2.mp4" \
  -F "files=@video3.mp4" \
  -F "operation=concat" \
  -F "output_format=mp4" \
  --output concatenated.mp4
```

### Example 2: Concatenate Videos with Fade Transitions
```bash
curl -X POST "http://localhost:8000/process-multi" \
  -F "files=@video1.mp4" \
  -F "files=@video2.mp4" \
  -F "operation=concat" \
  -F 'options={"transition": "fade", "duration": 1.5}' \
  -F "output_format=mp4" \
  --output faded_concat.mp4
```

### Example 3: Mix Multiple Audio Tracks
```bash
curl -X POST "http://localhost:8000/process-multi" \
  -F "files=@music.mp3" \
  -F "files=@vocals.wav" \
  -F "files=@drums.aac" \
  -F "operation=mix_audio" \
  -F 'options={"volumes": [1.0, 0.8, 0.6], "normalize": true}' \
  -F "output_format=mp3" \
  --output mixed_audio.mp3
```

### Example 4: Picture-in-Picture Video Overlay
```bash
curl -X POST "http://localhost:8000/process-multi" \
  -F "files=@main_video.mp4" \
  -F "files=@overlay_video.mp4" \
  -F "operation=overlay" \
  -F 'options={"positions": [{"x": 10, "y": 10}]}' \
  -F "output_format=mp4" \
  --output pip_video.mp4
```

### Example 5: Merge Separate Audio and Video Files
```bash
curl -X POST "http://localhost:8000/process-multi" \
  -F "files=@video_only.mp4" \
  -F "files=@audio_only.mp3" \
  -F "operation=merge_av" \
  -F 'options={"video_index": 0, "audio_index": 1}' \
  -F "output_format=mp4" \
  --output merged.mp4
```

### Example 6: Custom Multi-Input Operation
```bash
curl -X POST "http://localhost:8000/process-multi" \
  -F "files=@input1.mp4" \
  -F "files=@input2.mp4" \
  -F "operation=custom" \
  -F "command=-filter_complex [0:v][1:v]hstack=inputs=2" \
  -F "output_format=mp4" \
  --output side_by_side.mp4
```

## Operation Options

### Concatenation Options
```json
{
  "transition": "fade",  // Add fade transitions between clips
  "duration": 1.5        // Transition duration in seconds
}
```

### Audio Mixing Options
```json
{
  "volumes": [1.0, 0.8, 0.6],  // Volume levels for each input (0.0-1.0+)
  "normalize": true             // Apply audio normalization
}
```

### Video Overlay Options
```json
{
  "positions": [
    {"x": 10, "y": 10},     // Position for first overlay
    {"x": 100, "y": 50}     // Position for second overlay
  ]
}
```

### Audio/Video Merge Options
```json
{
  "video_index": 0,  // Index of file to use for video
  "audio_index": 1   // Index of file to use for audio
}
```

## Interactive API Documentation

Once the service is running, you can access the interactive API documentation at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Common FFmpeg Commands

Here are some common FFmpeg command patterns you can use:

### Video Processing:
- **Scale video**: `-vf scale=640:480`
- **Change quality**: `-crf 23` (lower = better quality)
- **Change codec**: `-c:v libx264` or `-c:v libx265`
- **Set preset**: `-preset fast` (ultrafast, fast, medium, slow, veryslow)

### Audio Processing:
- **Extract audio**: `-vn -acodec copy`
- **Change audio codec**: `-acodec mp3` or `-acodec aac`
- **Set audio bitrate**: `-ab 192k`
- **Remove audio**: `-an`

### Format Conversion:
- **MP4 to AVI**: `-c:v libx264 -c:a mp3`
- **WAV to MP3**: `-acodec mp3 -ab 192k`

## Error Handling

The API provides detailed error messages for common issues:
- Invalid FFmpeg commands
- Unsupported file formats
- Processing timeouts (5-minute limit)
- File size limitations

## Security Considerations

- The service runs FFmpeg commands in a containerized environment
- Temporary files are automatically cleaned up
- Processing has a 5-minute timeout to prevent resource exhaustion
- Consider implementing authentication for production use

## Development

### Running Locally (without Docker)

1. Install FFmpeg on your system
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python main.py
   ```

### Customization

You can modify the following in `main.py`:
- Processing timeout (currently 5 minutes)
- Temporary file locations
- API endpoints and parameters
- Error handling behavior 