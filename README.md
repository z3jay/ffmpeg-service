# FFmpeg Microservice API

A Docker-based microservice API for processing media files using FFmpeg commands.

## Features

- **RESTful API**: FastAPI-based service with automatic documentation
- **File Upload**: Accept media files via multipart/form-data
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

### Process Media File
- **POST** `/process` - Process a media file with FFmpeg

#### Parameters:
- `file` (required): Media file to process
- `command` (required): FFmpeg command (without input/output paths)
- `output_format` (optional): Output file extension (e.g., 'mp4', 'avi', 'wav')

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