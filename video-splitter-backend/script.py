import os
import subprocess
import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog

def get_video_duration(video_path):
    """Get the duration of the video in seconds using FFprobe."""
    cmd = [
        'ffprobe', 
        '-v', 'error', 
        '-show_entries', 'format=duration', 
        '-of', 'json', 
        video_path
    ]
    
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.stdout:
        try:
            data = json.loads(result.stdout)
            return float(data['format']['duration'])
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error parsing FFprobe output: {e}")
            return None
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
    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)
    
    # Get video duration
    duration = get_video_duration(video_path)
    if duration is None:
        print(f"Warning: Could not determine duration for {video_path}. Skipping file.")
        return
    
    print(f"Video duration: {duration:.2f} seconds")
    print(f"Selected segment length: {segment_length} seconds")
    
    # If the video is shorter than the segment length, just copy it
    if duration <= segment_length:
        output_path = os.path.join(output_folder, os.path.basename(video_path))
        print(f"Video is shorter than {segment_length} seconds. Copying without splitting.")
        cmd = ['ffmpeg', '-i', video_path, '-c', 'copy', output_path]
        subprocess.run(cmd)
        return
    
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
            print(f"Cannot split into reasonable segments. Copying without splitting.")
            cmd = ['ffmpeg', '-i', video_path, '-c', 'copy', output_path]
            subprocess.run(cmd)
            return
    else:
        is_even = True
    
    # Split the video
    video_name = Path(video_path).stem
    video_ext = Path(video_path).suffix
    
    if is_even:
        print(f"Splitting video into {best_segment_count} even segments of {best_segment_length:.2f} seconds each.")
        
        for i in range(best_segment_count):
            start_time = i * best_segment_length
            output_path = os.path.join(output_folder, f"{video_name}_part{i+1}{video_ext}")
            
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
            
            subprocess.run(cmd)
            print(f"Created segment {i+1}/{best_segment_count}: {output_path}")
    else:
        print(f"Splitting video into {best_segment_count} segments of {best_segment_length:.2f} seconds each (last segment may be longer).")
        
        last_segment_length = duration - (best_segment_count - 1) * best_segment_length
        
        for i in range(best_segment_count):
            start_time = i * best_segment_length
            
            # For the last segment, use the remaining duration
            if i == best_segment_count - 1:
                segment_duration = last_segment_length
            else:
                segment_duration = best_segment_length
                
            output_path = os.path.join(output_folder, f"{video_name}_part{i+1}{video_ext}")
            
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
            
            subprocess.run(cmd)
            print(f"Created segment {i+1}/{best_segment_count}: {output_path} ({segment_duration:.2f}s)")

def main():
    # Create a root window but hide it
    root = tk.Tk()
    root.withdraw()
    
    # Set default folder to Desktop
    desktop_path = os.path.expanduser("~/Desktop")
    
    # Open file dialog to select video
    print("Please select a video file in the file browser dialog...")
    video_path = filedialog.askopenfilename(
        title="Select Video File",
        initialdir=desktop_path,  # Start in Desktop folder
        filetypes=[
            ("Video files", "*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.webm *.m4v *.3gp"),
            ("All files", "*.*")
        ]
    )
    
    if not video_path:
        print("No video selected. Exiting.")
        return
    
    print(f"Selected: {video_path}")
    
    # Ask for output directory with file dialog too
    print("\nSelect where to save the clips in the next dialog...")
    output_dir = filedialog.askdirectory(
        title="Select Folder to Save Clips",
        initialdir=os.path.dirname(video_path)  # Start in the same folder as the selected video
    )
    
    if not output_dir:
        print("No output folder selected. Exiting.")
        return
        
    print(f"Output directory: {output_dir}")
    
    # Create output directory if it doesn't exist
    if not os.path.exists(output_dir):
        print(f"Output directory '{output_dir}' does not exist. Creating it...")
        try:
            os.makedirs(output_dir)
        except Exception as e:
            print(f"Error creating directory: {e}")
            return
    
    # Get video duration and determine segment length
    duration = get_video_duration(video_path)
    if duration is None:
        print(f"Error: Could not determine duration for {video_path}")
        return
    
    segment_length = determine_segment_length(duration)
    
    # Process the selected video
    try:
        split_video(video_path, output_dir, segment_length)
        print(f"\nFinished processing video. Clips saved to {output_dir}")
    except Exception as e:
        print(f"Error processing video: {e}")

if __name__ == "__main__":
    main()