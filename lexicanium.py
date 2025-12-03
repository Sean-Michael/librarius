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
from unstructured.partition.pdf import partition_pdf
import psycopg2
import click
import json

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_ARCHIVE_DIR = Path("./archive")
DEFAULT_DESTINATION = Path("./Data-Slates")
DEFAULT_PG_CREDS = Path("./pg-credentials.json")


def connect_db():
    try:
        with open(DEFAULT_PG_CREDS, 'r') as json_creds:
            creds = json.load(json_creds)
    except Exception as e:
        logger.error(e)
        exit(1)

    try:
        conn = psycopg2.connect(**creds)
        logger.info(f"Connected to PostgreSQL database {creds.get('dbname')} successfully")
        return conn
    except Exception as e:
        logger.error(e)
        exit(1)


def create_table(conn, name: str = "chunks"):
    cursor = conn.cursor()
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {name} (
            id SERIAL PRIMARY KEY,
            game VARCHAR(100),
            category VARCHAR(50),
            source_file VARCHAR(500),
            chunk_index INTEGER,
            content TEXT,
            element_type VARCHAR(100),
            embedding VECTOR(1536),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cursor.close()
    logger.info(f"Table '{name}' ready")


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


def insert_chunk(conn, game: str, category: str, source_file: str, chunk_index: int, content: str, element_type: str):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO chunks (game, category, source_file, chunk_index, content, element_type)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (game, category, source_file, chunk_index, content, element_type))
    conn.commit()
    cursor.close()


def categorize_pdf(pdf: Path) -> str:
    name = pdf.name.lower()
    if 'rules' in name or 'core' in name:
        return "rules"
    elif 'codex' in name:
        return "codices"
    return "misc"


def process_pdf(conn, game: str, category: str, pdf: Path):
    logger.info(f"Processing: {pdf.name}")
    elements = partition_pdf(str(pdf))
    for i, el in enumerate(elements):
        insert_chunk(conn, game, category, pdf.name, i, str(el), type(el).__name__)
    logger.info(f"Inserted {len(elements)} chunks from {pdf.name}")


def chunk_data_slates(dest, conn):
    directories = [d for d in dest.iterdir() if d.is_dir()]

    for game_dir in directories:
        pdf_files = list(game_dir.glob("*.pdf"))
        logger.info(f"Found {len(pdf_files)} PDFs for {game_dir.name}")

        for pdf in pdf_files:
            category = categorize_pdf(pdf)
            process_pdf(conn, game_dir.name, category, pdf)
                    

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

    conn = connect_db()
    create_table(conn)
    chunk_data_slates(dest, conn)
    conn.close()

if __name__ == "__main__":
    main()