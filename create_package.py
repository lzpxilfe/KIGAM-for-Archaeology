import os
import zipfile
import sys

def create_plugin_zip(output_path):
    # Source directory (current dir of script + KigamGeoDownloader)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    source_dir = os.path.join(base_dir, 'KigamGeoDownloader')
    
    # Files to include from the plugin folder
    files_to_pack = [
        '__init__.py',
        'main.py',
        'zip_processor.py',
        'geochem_utils.py',
        'kigam_api_client.py',
        'metadata.txt',
        'icon.png'
    ]
    
    # Top-level folder name in ZIP
    plugin_folder_name = 'KigamGeoDownloader'
    
    print(f"Creating ZIP package: {output_path}")
    
    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for filename in files_to_pack:
                src_path = os.path.join(source_dir, filename)
                if os.path.exists(src_path):
                    # ARCNAME is what defines the structure in the zip
                    # We prepend the plugin folder name
                    arcname = os.path.join(plugin_folder_name, filename)
                    zf.write(src_path, arcname)
                    print(f"  Added: {filename} -> {arcname}")
                else:
                    print(f"  WARNING: File not found: {src_path}")
            
            # Add LICENSE from root directory
            license_path = os.path.join(base_dir, 'LICENSE')
            if os.path.exists(license_path):
                arcname = os.path.join(plugin_folder_name, 'LICENSE')
                zf.write(license_path, arcname)
                print(f"  Added: LICENSE -> {arcname}")
            else:
                print(f"  WARNING: LICENSE not found: {license_path}")
        
        print("ZIP package created successfully.")
        
    except Exception as e:
        print(f"Error creating ZIP: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        output_path = sys.argv[1]
    else:
        # Default to Desktop
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        output_path = os.path.join(desktop, "KIGAM_for_Archaeology_v0.1.0.zip")
        
    create_plugin_zip(output_path)
