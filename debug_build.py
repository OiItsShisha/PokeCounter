import PyInstaller.__main__
import shutil
import os

# --- CONFIGURATION ---
APP_NAME = "PokePulse"
SPEC_FILE = "PokePulseDebug.spec"  # The spec file we just updated
DIST_FOLDER = "dist"
BUILD_FOLDER = "build"
OUTPUT_FOLDER = os.path.join(DIST_FOLDER, "PokePulse_App")
ZIP_NAME = "DebugPokePulse_v1.0"

def clean_old_builds():
    """Removes old build and dist folders to ensure a fresh start."""
    print("Cleaning old build files...")
    for folder in [DIST_FOLDER, BUILD_FOLDER]:
        if os.path.exists(folder):
            shutil.rmtree(folder)

def run_build():
    """Runs PyInstaller using the .spec file."""
    print(f"Starting build for {APP_NAME}...")
    PyInstaller.__main__.run([
        SPEC_FILE,
        '--noconfirm',
        '--clean'
    ])

def create_zip():
    """Zips the output folder."""
    print("Creating ZIP archive...")
    # This zips everything inside 'dist/PokePulse_App' into 'PokePulse_v1.0.zip'
    shutil.make_archive(ZIP_NAME, 'zip', OUTPUT_FOLDER)
    print(f"Success! Created {ZIP_NAME}.zip")

if __name__ == "__main__":
    clean_old_builds()
    run_build()
    create_zip()