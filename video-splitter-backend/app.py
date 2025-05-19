import os
import subprocess
import json
import tempfile
import shutil
import traceback
import logging
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# Allow requests from your Vite development server
CORS(app, origins=["*"])

# Create upload and output directories
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
OUTPUT_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB max upload size

def get_video_duration(video_path):
    """Get the duration of the video in seconds using FFprobe."""
    cmd = [
        'ffprobe', 
        '-v', 'error', 
        '-show_entries', 'format=duration', 
        '-of', 'json', 
        video_path
    ]
    
    logger.debug(f"Running FFprobe command: {' '.join(cmd)}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    if result.returncode != 0:
        logger.error(f"FFprobe error: {result.stderr}")
        return None
    
    if result.stdout:
        try:
            data = json.loads(result.stdout)
            duration = float(data['format']['duration'])
            logger.debug(f"Video duration: {duration} seconds")
            return duration
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error parsing FFprobe output: {e}")
            logger.error(f"FFprobe output: {result.stdout}")
            return None
    
    logger.error("No output from FFprobe")
    return None

def determine_segment_length(duration):
    """Automatically determine segment length based on video duration."""
    if duration > 120:  # Longer than 2 minutes
        return 15
    elif duration > 30:  # Between 30 seconds and 2 minutes
        return 13
    else:  # Very short videos
        return 10

def split_video(video_path, output_folder, segment_length):
    """Split the video into segments of specified length."""
    logger.info(f"Starting to split video: {video_path}")
    logger.info(f"Output folder: {output_folder}")
    logger.info(f"Target segment length: {segment_length}")
    
    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)
    
    # Get video duration
    duration = get_video_duration(video_path)
    if duration is None:
        error_msg = f"Could not determine duration for {video_path}"
        logger.error(error_msg)
        return {"error": error_msg}
    
    result = {
        "duration": duration,
        "segment_length": segment_length,
        "segments": []
    }
    
    # If the video is shorter than the segment length, just copy it
    if duration <= segment_length:
        output_path = os.path.join(output_folder, os.path.basename(video_path))
        cmd = ['ffmpeg', '-i', video_path, '-c', 'copy', output_path]
        logger.debug(f"Running FFmpeg command: {' '.join(cmd)}")
        
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if process.returncode != 0:
            logger.error(f"FFmpeg error: {process.stderr}")
            return {"error": f"FFmpeg error: {process.stderr}"}
        
        result["segments"].append({
            "path": os.path.basename(output_path),
            "duration": duration
        })
        return result
    
    # Try different number of segments to find one that fits our criteria
    best_segment_count = 0
    best_segment_length = 0
    acceptable_min = 9.5  # Slightly more flexible minimum
    acceptable_max = 15.5  # Slightly more flexible maximum
    
    # Try from 2 segments up to a reasonable maximum
    max_segments_to_try = int(duration / acceptable_min) + 1
    
    for num_segments in range(2, max_segments_to_try + 1):
        test_segment_length = duration / num_segments
        if acceptable_min <= test_segment_length <= acceptable_max:
            best_segment_count = num_segments
            best_segment_length = test_segment_length
            # If we're comfortably within our target range, stop here
            if 10 <= test_segment_length <= 15:
                break
    
    # If we couldn't find a good segment count, offer to use uneven segments as plan B
    if best_segment_count == 0:
        # Try forcing it to use the target segment length
        num_segments = int(duration / segment_length)
        if num_segments >= 1:
            # Make the last segment potentially longer
            best_segment_count = num_segments
            best_segment_length = segment_length
            is_even = False
        else:
            output_path = os.path.join(output_folder, os.path.basename(video_path))
            cmd = ['ffmpeg', '-i', video_path, '-c', 'copy', output_path]
            logger.debug(f"Running FFmpeg command: {' '.join(cmd)}")
            
            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if process.returncode != 0:
                logger.error(f"FFmpeg error: {process.stderr}")
                return {"error": f"FFmpeg error: {process.stderr}"}
            
            result["segments"].append({
                "path": os.path.basename(output_path),
                "duration": duration
            })
            return result
    else:
        is_even = True
    
    # Split the video
    video_name = Path(video_path).stem
    video_ext = Path(video_path).suffix
    
    logger.info(f"Splitting video into {best_segment_count} segments of ~{best_segment_length:.2f} seconds each")
    
    if is_even:
        result["segment_count"] = best_segment_count
        result["segment_length"] = best_segment_length
        result["is_even"] = True
        
        for i in range(best_segment_count):
            start_time = i * best_segment_length
            output_filename = f"{video_name}_part{i+1}{video_ext}"
            output_path = os.path.join(output_folder, output_filename)
            
            # Fixed FFmpeg command - using input seeking for better accuracy
            # and re-encoding to ensure proper output
            cmd = [
                'ffmpeg',
                '-ss', str(start_time),  # Seek from the beginning
                '-i', video_path,        # Input file
                '-t', str(best_segment_length), # Duration to extract
                '-c:v', 'libx264',       # Re-encode video to ensure proper keyframes
                '-c:a', 'aac',           # Re-encode audio
                '-preset', 'ultrafast',  # Fast encoding
                '-crf', '23',            # Decent quality
                output_path
            ]
            
            logger.debug(f"Running FFmpeg command: {' '.join(cmd)}")
            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            if process.returncode != 0:
                logger.error(f"FFmpeg error: {process.stderr}")
                return {"error": f"FFmpeg error: {process.stderr}"}
            
            result["segments"].append({
                "path": output_filename,
                "duration": best_segment_length,
                "start_time": start_time
            })
    else:
        result["segment_count"] = best_segment_count
        result["segment_length"] = best_segment_length
        result["is_even"] = False
        
        last_segment_length = duration - (best_segment_count - 1) * best_segment_length
        
        for i in range(best_segment_count):
            start_time = i * best_segment_length
            
            # For the last segment, use the remaining duration
            if i == best_segment_count - 1:
                segment_duration = last_segment_length
            else:
                segment_duration = best_segment_length
                
            output_filename = f"{video_name}_part{i+1}{video_ext}"
            output_path = os.path.join(output_folder, output_filename)
            
            # Fixed FFmpeg command
            cmd = [
                'ffmpeg',
                '-ss', str(start_time),  # Seek from the beginning
                '-i', video_path,        # Input file
                '-t', str(segment_duration), # Duration to extract
                '-c:v', 'libx264',       # Re-encode video to ensure proper keyframes
                '-c:a', 'aac',           # Re-encode audio
                '-preset', 'ultrafast',  # Fast encoding
                '-crf', '23',            # Decent quality
                output_path
            ]
            
            logger.debug(f"Running FFmpeg command: {' '.join(cmd)}")
            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            if process.returncode != 0:
                logger.error(f"FFmpeg error: {process.stderr}")
                return {"error": f"FFmpeg error: {process.stderr}"}
            
            result["segments"].append({
                "path": output_filename,
                "duration": segment_duration,
                "start_time": start_time
            })
    
    logger.info(f"Successfully split video into {len(result['segments'])} segments")
    return result

@app.route('/api/upload', methods=['POST', 'OPTIONS'])
def upload_file():
    if request.method == 'OPTIONS':
        # Handle preflight request
        return '', 204
        
    logger.info("Received file upload request")
    
    try:
        if 'file' not in request.files:
            logger.error("No file part in the request")
            return jsonify({"error": "No file part"}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            logger.error("No selected file")
            return jsonify({"error": "No selected file"}), 400
        
        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            logger.info(f"Saving uploaded file to {file_path}")
            file.save(file_path)
            
            # Get video duration and determine segment length
            logger.info(f"Getting duration for {filename}")
            duration = get_video_duration(file_path)
            if duration is None:
                error_msg = f"Could not determine duration for {filename}"
                logger.error(error_msg)
                return jsonify({"error": error_msg}), 400
            
            segment_length = determine_segment_length(duration)
            logger.info(f"Determined segment length: {segment_length}")
            
            # Create a unique output folder for this video
            video_id = Path(filename).stem
            output_dir = os.path.join(app.config['OUTPUT_FOLDER'], video_id)
            
            # Process the video
            try:
                logger.info(f"Processing video {filename}")
                result = split_video(file_path, output_dir, segment_length)
                
                if "error" in result:
                    logger.error(f"Error in split_video: {result['error']}")
                    return jsonify({"error": result["error"]}), 500
                
                logger.info("Video processing completed successfully")
                return jsonify({
                    "success": True,
                    "video_id": video_id,
                    "result": result
                })
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error processing video: {error_msg}")
                logger.error(traceback.format_exc())
                return jsonify({"error": error_msg}), 500
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Unexpected error in upload_file: {error_msg}")
        logger.error(traceback.format_exc())
        return jsonify({"error": error_msg}), 500

@app.route('/api/download/<video_id>/<filename>', methods=['GET', 'OPTIONS'])
def download_file(video_id, filename):
    if request.method == 'OPTIONS':
        # Handle preflight request
        return '', 204
        
    logger.info(f"Download request for {video_id}/{filename}")
    output_dir = os.path.join(app.config['OUTPUT_FOLDER'], video_id)
    return send_from_directory(output_dir, filename, as_attachment=True)

@app.route('/api/save-to-path', methods=['POST', 'OPTIONS'])
def save_to_path():
    if request.method == 'OPTIONS':
        # Handle preflight request
        return '', 204
        
    logger.info("Received save-to-path request")
    try:
        data = request.json
        if not data or 'video_id' not in data or 'path' not in data:
            logger.error("Missing video_id or path in request")
            return jsonify({"error": "Missing video_id or path"}), 400
        
        video_id = data['video_id']
        target_path = data['path']
        
        logger.info(f"Saving video {video_id} to path {target_path}")
        
        # Validate the target path
        if not os.path.exists(target_path) or not os.path.isdir(target_path):
            logger.error(f"Invalid target path: {target_path}")
            return jsonify({"error": "Invalid target path"}), 400
        
        # Source directory
        source_dir = os.path.join(app.config['OUTPUT_FOLDER'], video_id)
        if not os.path.exists(source_dir):
            logger.error(f"Video segments not found: {source_dir}")
            return jsonify({"error": "Video segments not found"}), 404
        
        # Copy all files from source to target
        try:
            files_copied = []
            for filename in os.listdir(source_dir):
                source_file = os.path.join(source_dir, filename)
                target_file = os.path.join(target_path, filename)
                logger.info(f"Copying {source_file} to {target_file}")
                shutil.copy2(source_file, target_file)
                files_copied.append(filename)
            
            logger.info(f"Successfully copied {len(files_copied)} files to {target_path}")
            return jsonify({
                "success": True,
                "message": f"Copied {len(files_copied)} files to {target_path}",
                "files": files_copied
            })
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error copying files: {error_msg}")
            logger.error(traceback.format_exc())
            return jsonify({"error": error_msg}), 500
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Unexpected error in save_to_path: {error_msg}")
        logger.error(traceback.format_exc())
        return jsonify({"error": error_msg}), 500

@app.route('/', methods=['GET', 'OPTIONS'])
def index():
    if request.method == 'OPTIONS':
        # Handle preflight request
        return '', 204
    
    # Simple status response
    return jsonify({"status": "API is running"})

if __name__ == "__main__":
    logger.info("Starting Flask server")
    # Use 0.0.0.0 to allow external connections
    app.run(host='0.0.0.0', debug=True, port=5000)