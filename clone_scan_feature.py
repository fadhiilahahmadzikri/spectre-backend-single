import os
import shutil
import json

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# Define the root directory where both frontend projects are located.
# The script assumes it is being run from the parent directory of the projects.
# For example, if projects are in D:\spectre\spectre-frontend and D:\spectre\spectre-snap,
# this script should be run from D:\spectre.
BASE_DIR = os.getcwd()
SOURCE_ROOT = os.path.join(BASE_DIR, "spectre-frontend")
DEST_ROOT = os.path.join(BASE_DIR, "spectre-snap")

# Define the manifest of files and directories to be cloned.
# Paths are relative to the 'src' directory, unless otherwise specified.
CLONE_MANIFEST = {
    "dirs": [
        "features/face-scan",
        "shared/ui/GlassDialog",
        "shared/ui/GlassDrawer",
    ],
    "files": [
        "pages/FaceScan.tsx",
        "components/ui/alert.tsx",
        "components/ui/button.tsx",
        "components/ui/dialog.tsx",
        "components/ui/spinner.tsx",
        "components/ui/switch.tsx",
        "lib/api.ts",
        "lib/config.ts",
        "lib/store.ts",
        "lib/utils.ts",
        "shared/config/scan.config.ts",
        "shared/hooks/use-script-loader.ts",
        "shared/icons/FaceIDGlyph.tsx",
        "shared/icons/index.ts",
        "shared/icons/poc-icons.tsx",
        "shared/lib/copy/index.ts",
        "shared/lib/copy/scan.ts",
        "shared/lib/http/abortable-request.ts",
        "shared/lib/http/index.ts",
    ],
    "root_files": [
        # Files located in the root of the source project, like config files.
        "tailwind.config.js", # Assuming .js, adjust if it's .ts or other
        "postcss.config.js",
    ],
    "public_files": [
        "logo.svg",
    ]
}

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def log(message, level="INFO"):
    """Simple logger."""
    print(f"[{level.upper()}] {message}")

def copy_item(src_path, dst_path):
    """Copies a file or a directory from source to destination."""
    try:
        # Ensure the parent directory of the destination exists.
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        
        if os.path.isdir(src_path):
            # If destination exists, remove it to ensure a fresh copy.
            if os.path.exists(dst_path):
                shutil.rmtree(dst_path)
            shutil.copytree(src_path, dst_path)
            log(f"Copied directory: {src_path} -> {dst_path}")
        elif os.path.isfile(src_path):
            shutil.copy2(src_path, dst_path) # copy2 preserves metadata
            log(f"Copied file: {src_path} -> {dst_path}")
        else:
            log(f"Source path not found: {src_path}", level="WARN")
    except Exception as e:
        log(f"Error copying {src_path}: {e}", level="ERROR")

def merge_package_json():
    """Merges dependencies from source package.json to destination."""
    log("Starting package.json merge...")
    src_pkg_path = os.path.join(SOURCE_ROOT, "package.json")
    dst_pkg_path = os.path.join(DEST_ROOT, "package.json")

    if not os.path.exists(src_pkg_path):
        log("Source package.json not found. Skipping merge.", level="WARN")
        return

    if not os.path.exists(dst_pkg_path):
        log("Destination package.json not found. Skipping merge.", level="WARN")
        return
        
    try:
        with open(src_pkg_path, "r", encoding="utf-8") as f:
            src_data = json.load(f)
        with open(dst_pkg_path, "r", encoding="utf-8") as f:
            dst_data = json.load(f)

        # Ensure dependency keys exist
        if "dependencies" not in dst_data:
            dst_data["dependencies"] = {}
        if "devDependencies" not in dst_data:
            dst_data["devDependencies"] = {}

        # Merge dependencies and devDependencies
        dst_data["dependencies"].update(src_data.get("dependencies", {}))
        dst_data["devDependencies"].update(src_data.get("devDependencies", {}))
        
        # Sort keys for readability
        dst_data["dependencies"] = dict(sorted(dst_data["dependencies"].items()))
        dst_data["devDependencies"] = dict(sorted(dst_data["devDependencies"].items()))

        with open(dst_pkg_path, "w", encoding="utf-8") as f:
            json.dump(dst_data, f, indent=2)
        
        log("Successfully merged dependencies into destination package.json.")

    except Exception as e:
        log(f"Failed to merge package.json files: {e}", level="ERROR")

def merge_css_variables():
    """
    Extracts CSS variables from source index.css and prepends them
    to the destination index.css.
    """
    log("Starting CSS variable merge...")
    src_css_path = os.path.join(SOURCE_ROOT, "src", "index.css")
    dst_css_path = os.path.join(DEST_ROOT, "src", "index.css")

    if not os.path.exists(src_css_path):
        log("Source index.css not found. Skipping merge.", level="WARN")
        return

    if not os.path.exists(dst_css_path):
        log("Destination index.css not found. Creating it.", level="INFO")
        os.makedirs(os.path.dirname(dst_css_path), exist_ok=True)
        with open(dst_css_path, "w", encoding="utf-8") as f:
            f.write("") # Create empty file

    try:
        with open(src_css_path, "r", encoding="utf-8") as f:
            src_content = f.read()
        
        # A simple way to find the :root block
        start_marker = ":root {"
        end_marker = "}"
        start_index = src_content.find(start_marker)
        
        if start_index == -1:
            log("No :root block found in source index.css. Skipping.", level="WARN")
            return
            
        end_index = src_content.find(end_marker, start_index)
        css_vars_block = src_content[start_index : end_index + 1]

        with open(dst_css_path, "r+", encoding="utf-8") as f:
            dst_content = f.read()
            if css_vars_block not in dst_content:
                f.seek(0, 0)
                f.write(css_vars_block + "\n\n" + dst_content)
                log("Successfully merged CSS variables into destination index.css.")
            else:
                log("CSS variables already exist in destination index.css. Skipping.", level="INFO")

    except Exception as e:
        log(f"Failed to merge CSS variables: {e}", level="ERROR")


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

def main():
    """Main function to run the cloning process."""
    log("Starting Spectre-Snap migration script.")
    log(f"Source root: {SOURCE_ROOT}")
    log(f"Destination root: {DEST_ROOT}")

    # --- Copy directories from 'src' ---
    for dir_name in CLONE_MANIFEST["dirs"]:
        src = os.path.join(SOURCE_ROOT, "src", dir_name)
        dst = os.path.join(DEST_ROOT, "src", dir_name)
        copy_item(src, dst)

    # --- Copy individual files from 'src' ---
    for file_path in CLONE_MANIFEST["files"]:
        src = os.path.join(SOURCE_ROOT, "src", file_path)
        dst = os.path.join(DEST_ROOT, "src", file_path)
        copy_item(src, dst)

    # --- Copy root-level config files ---
    for file_name in CLONE_MANIFEST["root_files"]:
        src = os.path.join(SOURCE_ROOT, file_name)
        dst = os.path.join(DEST_ROOT, file_name)
        if os.path.exists(src):
            copy_item(src, dst)
        else:
            log(f"Optional root config not found, skipping: {src}", level="INFO")

    # --- Copy files from 'public' ---
    for file_name in CLONE_MANIFEST["public_files"]:
        src = os.path.join(SOURCE_ROOT, "public", file_name)
        dst = os.path.join(DEST_ROOT, "public", file_name)
        copy_item(src, dst)

    # --- Post-processing steps ---
    merge_package_json()
    merge_css_variables()
    
    log("Migration script finished successfully!")
    log("Next steps:")
    log("1. Navigate to the 'spectre-snap' directory.")
    log("2. Run 'npm install' or 'pnpm install' to install dependencies.")
    log("3. Run 'npm run dev' to start the development server.")
    log("4. You may need to create a new entry point in 'spectre-snap/src/main.tsx' to render the 'FaceScan' page.")

if __name__ == "__main__":
    main()
