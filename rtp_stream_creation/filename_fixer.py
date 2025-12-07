from pathlib import Path
import shutil
import tempfile

def sync_frame_names(source_folder, target_folder, output_folder=None):
    """
    Copies and renames files from target_folder to match the naming pattern of source_folder.
    Safely handles naming conflicts by using a temporary staging area.
    
    Args:
        source_folder: Folder with missing frames (defines the naming pattern)
        target_folder: Folder with consecutive frames (to be renamed)
        output_folder: Optional. If provided, copies to new folder. Otherwise, renames in place.
    """
    source_path = Path(source_folder)
    target_path = Path(target_folder)
    
    # Get sorted list of PNG files from both folders
    source_files = sorted(source_path.glob("*.png"))
    target_files = sorted(target_path.glob("*.png"))
    
    if len(source_files) != len(target_files):
        print(f"WARNING: File count mismatch!")
        print(f"Source folder has {len(source_files)} files")
        print(f"Target folder has {len(target_files)} files")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            return
    
    # Use the minimum count to avoid index errors
    num_files = min(len(source_files), len(target_files))
    
    # Determine final output location
    if output_folder:
        final_output = Path(output_folder)
        final_output.mkdir(parents=True, exist_ok=True)
        print(f"Copying {num_files} files to {final_output} with new names...")
        
        # Direct copy to output folder (no conflicts possible)
        for i in range(num_files):
            source_name = source_files[i].name
            target_file = target_files[i]
            new_path = final_output / source_name
            shutil.copy2(target_file, new_path)
            print(f"Copied: {target_file.name} -> {source_name}")
    else:
        print(f"Renaming {num_files} files in place...")
        
        # Use temporary staging to avoid conflicts
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Step 1: Copy all files to temp with new names
            print("Step 1: Staging files with new names...")
            for i in range(num_files):
                source_name = source_files[i].name
                target_file = target_files[i]
                temp_file = temp_path / source_name
                shutil.copy2(target_file, temp_file)
                print(f"  Staged: {target_file.name} -> {source_name}")
            
            # Step 2: Remove original files from target
            print("\nStep 2: Removing original files...")
            for target_file in target_files:
                target_file.unlink()
                print(f"  Removed: {target_file.name}")
            
            # Step 3: Move renamed files from temp back to target
            print("\nStep 3: Moving renamed files back...")
            for temp_file in temp_path.glob("*.png"):
                final_path = target_path / temp_file.name
                shutil.move(str(temp_file), str(final_path))
                print(f"  Moved: {temp_file.name}")
    
    print(f"\nDone! Processed {num_files} files.")

if __name__ == "__main__":
    base_path = Path(__file__).parent.resolve()
    games = ["Fortnite", "Forza", "Kombat"]
    bandwidths = ["2Mbit", "4Mbit", "6Mbit", "8Mbit", "10Mbit"]
    
    for game in games:
        for bdwidth in bandwidths:
            source = base_path.parent / "acm_tomm_experiments" / "reference_vs_synth" / game / f"{bdwidth}_{game}" / "received_frames"
            target = base_path.parent / "rtp_stream_creation" / "result_frames" / game / f"{bdwidth}_{game}"
            output = None  # Or specify an output folder if desired, in that case the target folder remains unchanged and a new folder with the correct names is created.
    
            sync_frame_names(source, target, output)