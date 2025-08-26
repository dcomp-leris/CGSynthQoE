#!/usr/bin/env python3
"""
Frame Extraction Script
Extracts frames from MP4 video files at 30 FPS.
"""

import cv2
import os
import argparse
from pathlib import Path


def extract_frames(video_path, output_dir=None, target_fps=30):
    """
    Extract frames from a video file at the specified FPS.
    
    Args:
        video_path (str): Path to the input MP4 file
        output_dir (str): Directory to save extracted frames (default: video_name_frames)
        target_fps (int): Target FPS for frame extraction (default: 30)
    
    Returns:
        int: Number of frames extracted
    """
    # Validate input file
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    # Create output directory
    if output_dir is None:
        video_name = Path(video_path).stem
        output_dir = f"{video_name}_frames"
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Open video capture
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {video_path}")
    
    # Get video properties
    original_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / original_fps
    
    print(f"Video info:")
    print(f"  Original FPS: {original_fps:.2f}")
    print(f"  Total frames: {total_frames}")
    print(f"  Duration: {duration:.2f} seconds")
    print(f"  Target FPS: {target_fps}")
    
    # Calculate frame interval for target FPS
    frame_interval = original_fps / target_fps
    
    frame_count = 0
    extracted_count = 0
    
    while True:
        ret, frame = cap.read()
        
        if not ret:
            break
        
        # Check if this frame should be extracted based on target FPS
        if frame_count % int(frame_interval) == 0:
            # Generate frame filename with zero-padding
            frame_filename = os.path.join(output_dir, f"frame_{extracted_count:06d}.jpg")
            
            # Save frame
            cv2.imwrite(frame_filename, frame)
            extracted_count += 1
            
            if extracted_count % 100 == 0:
                print(f"Extracted {extracted_count} frames...")
        
        frame_count += 1
    
    cap.release()
    
    print(f"\nExtraction complete!")
    print(f"  Extracted {extracted_count} frames")
    print(f"  Saved to: {output_dir}")
    print(f"  Effective FPS: {extracted_count / duration:.2f}")
    
    return extracted_count


def main():
    parser = argparse.ArgumentParser(description="Extract frames from MP4 video at specified FPS")
    parser.add_argument("video_path", help="Path to the input MP4 file")
    parser.add_argument("-o", "--output", help="Output directory for frames")
    parser.add_argument("-f", "--fps", type=int, default=30, help="Target FPS (default: 30)")
    
    args = parser.parse_args()
    
    try:
        extract_frames(args.video_path, args.output, args.fps)
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
