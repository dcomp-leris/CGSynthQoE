import os
import cv2
import sys
import argparse

# Default settings
original_res = [1920, 1080]
# `original_folder` may be overridden from command-line arguments later
original_folder = f"original_frames_{original_res[0]}_{original_res[1]}"
target_downscaled_res = [1600, 900]
target_upscaled_res = [1920, 1080]


def get_downscaled_folder():
    """Return folder name for downscaled images based on current settings."""
    return (f"downscaled_original_frames_from_{original_res[0]}_{original_res[1]}_"
            f"to_{target_downscaled_res[0]}_{target_downscaled_res[1]}")


def get_upscaled_folder():
    """Return folder name for upscaled images based on current settings."""
    return (f"upscaled_original_frames_from_{target_downscaled_res[0]}_{target_downscaled_res[1]}_"
            f"to_{target_upscaled_res[0]}_{target_upscaled_res[1]}")


def downscale_images():
    downscaled_folder = get_downscaled_folder()
    os.makedirs(downscaled_folder, exist_ok=True)

    if not os.path.exists(original_folder):
        print(f"[ERROR] Folder '{original_folder}' does not exist.")
        sys.exit(1)

    image_files = [f for f in os.listdir(original_folder) if f.endswith('.png')]

    if not image_files:
        print(f"[WARNING] No PNG images found in '{original_folder}'.")

    for image_file in image_files:
        image_path = os.path.join(original_folder, image_file)
        image = cv2.imread(image_path)
        if image is None:
            print(f"Skipped {image_file}: could not read file.")
            continue

        # Resize to target downscaled resolution
        image_resized = cv2.resize(image, target_downscaled_res, interpolation=cv2.INTER_AREA)
        
        # Save downscaled image
        downscaled_path = os.path.join(downscaled_folder, image_file)
        cv2.imwrite(downscaled_path, image_resized)

    print(f"Downscaled {len(image_files)} images to {target_downscaled_res}.")


def upscale_images():
    downscaled_folder = get_downscaled_folder()
    upscaled_folder = get_upscaled_folder()

    if not os.path.exists(downscaled_folder):
        print(f"[ERROR] Folder '{downscaled_folder}' does not exist.")
        print("Please downscale the images first or ensure the folder name is correct.")
        sys.exit(1)

    if not os.path.exists(original_folder):
        print(f"[ERROR] Folder '{original_folder}' does not exist.")
        sys.exit(1)

    os.makedirs(upscaled_folder, exist_ok=True)
    image_files = [f for f in os.listdir(original_folder) if f.endswith('.png')]

    for image_file in image_files:
        downscaled_path = os.path.join(downscaled_folder, image_file)
        
        # Load original for size reference
        #original_image = cv2.imread(original_path)
        #original_shape = (original_image.shape[1], original_image.shape[0])  # width, height
        upscaled_shape = (target_upscaled_res[0], target_upscaled_res[1])

        # Load the downscaled image
        if not os.path.exists(downscaled_path):
            print(f"Skipped {image_file}: Downscaled version not found.")
            continue

        downscaled_image = cv2.imread(downscaled_path)

        # Resize back to original shape
        image_upscaled = cv2.resize(downscaled_image, upscaled_shape, interpolation=cv2.INTER_CUBIC)
        
        # Save upscaled image
        upscaled_path = os.path.join(upscaled_folder, image_file)
        cv2.imwrite(upscaled_path, image_upscaled)

    print(f"Upscaled {len(image_files)} images back to original resolution.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Downscale or upscale PNG images.")
    parser.add_argument("mode", choices=["down", "up"], help="down: downscale, up: upscale from downscaled")
    parser.add_argument("--folder", "-f", dest="folder", default=None,
                        help="Path to folder containing original PNG frames. If omitted, defaults to original_frames_<WxH>.")
    args = parser.parse_args()

    # Override original_folder if provided
    if args.folder:
        original_folder = args.folder  # override default folder

    if args.mode == "down":
        downscale_images()
    else:
        upscale_images()

    cv2.destroyAllWindows()
