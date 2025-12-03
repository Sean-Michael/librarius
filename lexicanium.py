'''
lexicanium 
    - extracts .zip files from archive into Data-Slates
    - Data-Slates are loaded into vector database
'''

import concurrent.futures
import time
import zipfile
from pathlib import Path
import logging
import unstructured
import click

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_ARCHIVE_DIR = Path("./archive")
DEFAULT_DESTINATION = Path("./Data-Slates")


def extract_zip(filepath: Path, destination: Path) -> bool:
    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            zf.extractall(destination)
        return True
    except Exception as e:
        logger.error(f'ERROR: {e}')
        return False


def proc_load_from_archive(zip_paths: list[Path], destination: Path) -> list[Path]:
    extracted = []
    with concurrent.futures.ProcessPoolExecutor() as executor:
        future_to_zip = {executor.submit(extract_zip, filepath, destination): filepath for filepath in zip_paths}
        for future in concurrent.futures.as_completed(future_to_zip):
            data = future_to_zip[future]
            try:
                future.result()
                extracted.append(data)
                logger.info(f'Extracted: {data}')
            except Exception as e:
                logger.error(f'ERROR: {e}')
    return extracted


def chunk_data_slates(dest):
    # Make a new directory for the processed chunks?
    # Actually just write them to postgres db
    directories = [d for d in dest.iterdir() if d.is_dir()]
    
    # So each game is going to be represented by a top level dir in Data-Slates/
    reliquary = {}

    for game in directories:
        reliquary[game] = {
            "rules": [],
            "codices": [],
            "misc": []
        }
        pdf_files = list(game.glob("*.pdf"))
        logger.info(f"Found {len(pdf_files)} PDFs for {game.name}")
        for pdf in pdf_files:
            if 'rules' in pdf.name.lower() or 'core' in pdf.name.lower():
                reliquary[game]["rules"].append(pdf)
            elif 'codex' in pdf.name.lower():
                reliquary[game]["codices"].append(pdf)
            else:
                reliquary[game]["misc"].append(pdf)
        logger.info(f"{game}\n\tRules: {reliquary[game].get('rules')}\n\tCodices: {reliquary[game].get('codices')}\n\tMisc: {reliquary[game].get('misc')}")

                    

@click.command()
@click.option('--source', '-s', type=click.Path(exists=True, path_type=Path),
              default=DEFAULT_ARCHIVE_DIR, help='Directory containing zip files')
@click.option('--dest', '-d', type=click.Path(path_type=Path),
              default=DEFAULT_DESTINATION, help='Destination directory for extraction')
@click.option('--skip-extract', is_flag=True, help='Skip zip extraction, process existing Data-Slates only')
def main(source: Path, dest: Path, skip_extract: bool) -> None:
    """Extract zip files from archive directory into Data-Slates."""
    dest.mkdir(parents=True, exist_ok=True)

    if not skip_extract:
        zip_paths = list(source.glob("*.zip"))
        if not zip_paths:
            logger.warning(f'No zip files found in {source}')
            return

        start_time = time.perf_counter()
        extracted = proc_load_from_archive(zip_paths, dest)
        elapsed = time.perf_counter() - start_time
        logger.info(f'Extracted {len(extracted)} archives in: {elapsed:.2f} seconds')

    chunk_data_slates(dest)

if __name__ == "__main__":
    main()