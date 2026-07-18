#!/usr/bin/env python3

"""
Input: Frames folder; Output: Video file
"""

import os
import subprocess
import argparse
import glob

class FramesToVideoConverter:
    def __init__(self, frames_folder, output_file=None, fps=30, force_glob=False):
        """
        Initialize the frames to video converter.

        Args:
            frames_folder (str): Path to the folder containing frames
            output_file (str): Path to the output video file (default: based on folder name)
            fps (int): Frames per second for the output video
            force_glob (bool): Use a glob pattern instead of a numbered sequence.
                Robust to gaps in numbered frames (e.g. dropped frames), which would
                otherwise make ffmpeg's sequence demuxer stop at the first missing index.
        """
        self.frames_folder = frames_folder
        self.fps = fps
        self.force_glob = force_glob
        
        if output_file is None:
            # Use folder name as base for output
            folder_basename = os.path.basename(os.path.normpath(frames_folder))
            output_file = f"{folder_basename}.mp4"
        self.output_file = output_file
        
        # Validate frames folder exists
        if not os.path.exists(frames_folder):
            raise ValueError(f"Frames folder does not exist: {frames_folder}")
        if not os.path.isdir(frames_folder):
            raise ValueError(f"Path is not a directory: {frames_folder}")
    
    def find_frame_pattern(self):
        """
        Find the appropriate frame pattern for ffmpeg input.
        
        Returns:
            tuple: (pattern, frame_count) or (None, 0) if no frames found
        """
        # Common frame file patterns
        patterns = [
            "*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tiff", "*.tif"
        ]
        
        for pattern in patterns:
            frame_files = glob.glob(os.path.join(self.frames_folder, pattern))
            if frame_files:
                # Sort to get consistent ordering
                frame_files.sort()
                print(f"Found {len(frame_files)} frames with pattern {pattern}")

                # Glob mode: collect every present frame regardless of gaps in
                # a numbered sequence (ffmpeg expands the glob and sorts itself).
                if self.force_glob:
                    return os.path.join(self.frames_folder, pattern), len(frame_files)

                # Determine if frames follow a sequence pattern (e.g., frame_001.jpg)
                first_file = os.path.basename(frame_files[0])
                
                # Try to detect common naming patterns
                if any(char.isdigit() for char in first_file):
                    # Has numbers, try to create ffmpeg pattern
                    base_name = first_file
                    # Replace numbers with %0Xd pattern
                    import re
                    
                    # Find sequences of digits
                    digit_matches = list(re.finditer(r'\d+', base_name))
                    if digit_matches:
                        # Use the last (usually longest) digit sequence
                        match = digit_matches[-1]
                        digit_count = len(match.group())
                        ffmpeg_pattern = (base_name[:match.start()] + 
                                        f"%0{digit_count}d" + 
                                        base_name[match.end():])
                        return os.path.join(self.frames_folder, ffmpeg_pattern), len(frame_files)
                
                # Fallback: use glob pattern for ffmpeg
                return os.path.join(self.frames_folder, pattern), len(frame_files)
        
        return None, 0
    
    def convert_to_video(self):
        """
        Convert frames to video using FFmpeg.
        
        Returns:
            bool: True if conversion was successful, False otherwise
        """
        pattern, frame_count = self.find_frame_pattern()
        
        if pattern is None:
            print(f"No image frames found in {self.frames_folder}")
            return False
        
        print(f"Converting {frame_count} frames to video at {self.fps} FPS...")
        print(f"Input pattern: {pattern}")
        print(f"Output file: {self.output_file}")
        
        try:
            # Build ffmpeg command based on pattern type
            if "*" in pattern:
                # Glob pattern
                cmd = [
                    "ffmpeg", "-y",
                    "-loglevel", "error",
                    "-framerate", str(self.fps),
                    "-pattern_type", "glob",
                    "-i", pattern,
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-crf", "18",  # High quality
                    self.output_file
                ]
            else:
                # Sequence pattern
                cmd = [
                    "ffmpeg", "-y",
                    "-loglevel", "error",
                    "-framerate", str(self.fps),
                    "-i", pattern,
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-crf", "18",  # High quality
                    self.output_file
                ]
            
            print(f"Running: {' '.join(cmd)}")
            process = subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            if os.path.exists(self.output_file):
                file_size = os.path.getsize(self.output_file)
                print(f"Successfully created video: {self.output_file} ({file_size} bytes)")
                return True
            else:
                print("Video file was not created")
                return False
                
        except subprocess.CalledProcessError as e:
            print(f"Error converting frames to video: {e}")
            if e.stderr:
                print(f"FFmpeg error: {e.stderr}")
            return False
        except Exception as e:
            print(f"Unexpected error: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description="Convert frames in a folder to an MP4 video")
    parser.add_argument("frames_folder", help="Path to folder containing image frames")
    parser.add_argument("-f", "--fps", type=int, default=30, 
                        help="Frames per second for output video (default: 30)")
    parser.add_argument("-o", "--output",
                        help="Output video file (default: based on folder name)")
    parser.add_argument("--glob", action="store_true",
                        help="Use a glob pattern instead of a numbered sequence "
                             "(robust to gaps from dropped frames)")

    args = parser.parse_args()

    try:
        converter = FramesToVideoConverter(
            frames_folder=args.frames_folder,
            output_file=args.output,
            fps=args.fps,
            force_glob=args.glob
        )
        
        success = converter.convert_to_video()
        if success:
            print("Video conversion completed successfully!")
        else:
            print("Video conversion failed.")
            exit(1)
            
    except ValueError as e:
        print(f"Error: {e}")
        exit(1)


if __name__ == "__main__":
    main()