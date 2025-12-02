'''
lexicanium 
    - extracts .zip files from archive into Data-Slates
    - Data-Slates are loaded into vector database
'''

import concurrent.futures
import time
import zipfile
import os
import shutil

zip_file_dir = "./archive"
destination_directory = "./Data-Slates"

def load_from_archive(zip_paths):

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


def extract_zip(filepath):
    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            zf.extractall(destination_directory)
    except Exception as e:
        print(f'ERROR: {e}')


def proc_load_from_archive(zip_paths):
    with concurrent.futures.ProcessPoolExecutor() as executor:
        future_to_zip = {executor.submit(extract_zip, filepath): filepath for filepath in zip_paths}
        for future in concurrent.futures.as_completed(future_to_zip):
            data = future_to_zip[future]
            try:
                future.result()
                print(f'Extracted: {data}')
            except Exception as e:
                print(f'ERROR: {e}')


def main():
    if not os.path.exists(destination_directory):
        os.makedirs(destination_directory)

    if not os.path.exists(zip_file_dir):
        print(f'Heretical path detected: {zip_file_dir}')
        exit(1)

    zip_paths = [os.path.join(zip_file_dir, filepath) for filepath in os.listdir(zip_file_dir)]


    start_thread_time = time.perf_counter()
    load_from_archive(zip_paths)
    end_thread_time = time.perf_counter()
    elapsed_thread_time = end_thread_time - start_thread_time
    print(f'Thread team finished in {elapsed_thread_time}')
   
    shutil.rmtree(os.path.join(destination_directory))

    start_proc_time = time.perf_counter()
    proc_load_from_archive(zip_paths)
    end_proc_time = time.perf_counter()
    elapsed_proc_time = end_proc_time - start_proc_time
    print(f'Process team finished in: {elapsed_proc_time}')


if __name__ == "__main__":
    main()