'''
lexicanium - extracts .zip files from archive into Data-Slates
'''

import zipfile
import os

zip_file_dir = "./archive"
destination_directory = "./Data-Slates"

def main():

    if not os.path.exists(destination_directory):
        os.makedirs(destination_directory)

    zip_files = [os.path.join(zip_file_dir, filepath) for filepath in os.listdir(zip_file_dir)]

    print(f'Found {len(zip_files)} .zip files in {zip_file_dir}')

    for filename in zip_files:
        try:
            with zipfile.ZipFile(filename, 'r') as zf:
                zf.extractall(destination_directory)
        except Exception as e:
            print(f"ERROR: {e}")
    
    print(os.listdir(destination_directory))



if __name__ == "__main__":
    main()