'''
lexicanium 
    - extracts .zip files from archive into Data-Slates
    - Data-Slates are loaded into vector database
'''

import concurrent.futures
import time
import zipfile
import os

zip_file_dir = "./archive"
destination_directory = "./Data-Slates"

def load_from_archive():
    if not os.path.exists(destination_directory):
        os.makedirs(destination_directory)

    zip_paths = [os.path.join(zip_file_dir, filepath) for filepath in os.listdir(zip_file_dir)]

    print(f'Found {len(zip_paths)} .zip files in {zip_file_dir}')

    zip_files = [zipfile.ZipFile(filename, 'r') for filename in zip_paths]

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_zip = {executor.submit(zf.extractall, destination_directory): zf for zf in zip_files}
        for future in concurrent.futures.as_completed(future_to_zip):
            data = future_to_zip[future]
            try:
                future.result()
                print(f'Extracted: {data}')
            except Exception as e:
                print(f'ERROR: {e}')
            future_to_zip[future].close()

    return os.listdir(destination_directory)
    


def main():
    load_from_archive()



if __name__ == "__main__":
    main()