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
from psycopg2 import pool
import psycopg2.extras
import click
import json

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_ARCHIVE_DIR = Path("./archive")
DEFAULT_DESTINATION = Path("./Data-Slates")
DEFAULT_PG_CREDS = Path("./pg-credentials.json")


def load_db_creds() -> dict:
    try:
        with open(DEFAULT_PG_CREDS, 'r') as json_creds:
            return json.load(json_creds)
    except Exception as e:
        logger.error(e)
        exit(1)


def create_connection_pool(min_conn: int = 2, max_conn: int = 10) -> pool.ThreadedConnectionPool:
    creds = load_db_creds()
    try:
        conn_pool = pool.ThreadedConnectionPool(min_conn, max_conn, **creds)
        logger.info(f"Connection pool created for {creds.get('dbname')}")
        return conn_pool
    except Exception as e:
        logger.error(e)
        exit(1)


def setup_database(conn, table_name: str = "chunks"):
    cursor = conn.cursor()
    try:
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
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
        logger.info(f"Database setup complete, table '{table_name}' ready")
    except Exception as e:
        logger.error(f"Failed to setup database: {e}")
        conn.rollback()
    finally:
        cursor.close()


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


def insert_chunks_batch(conn, chunks: list[tuple]):
    cursor = conn.cursor()
    try:
        psycopg2.extras.execute_values(
            cursor,
            """
            INSERT INTO chunks (game, category, source_file, chunk_index, content, element_type)
            VALUES %s
            """,
            chunks,
            page_size=100
        )
        conn.commit()
        logger.info(f"Inserted batch of {len(chunks)} chunks")
    except Exception as e:
        logger.error(f"Failed to insert batch: {e}")
        conn.rollback()
    finally:
        cursor.close()


def categorize_pdf(pdf: Path) -> str:
    name = pdf.name.lower()
    if 'rules' in name or 'core' in name:
        return "rules"
    elif 'codex' in name:
        return "codices"
    return "misc"


def process_pdf(pool: pool.ThreadedConnectionPool, game: str, category: str, pdf: Path):
    logger.info(f"Processing: {pdf.name}")
    elements = partition_pdf(str(pdf))
    chunks = [
        (game, category, pdf.name, i, str(el), type(el).__name__)
        for i, el in enumerate(elements)
    ]
    conn = pool.getconn()
    try:
        insert_chunks_batch(conn, chunks)
        logger.info(f"Inserted {len(elements)} chunks from {pdf.name}")
    finally:
        pool.putconn(conn)


def chunk_data_slates(dest: Path, conn_pool: pool.ThreadedConnectionPool, max_workers: int = 4):
    directories = [d for d in dest.iterdir() if d.is_dir()]

    pdf_tasks = []
    for game_dir in directories:
        pdf_files = list(game_dir.glob("*.pdf"))
        logger.info(f"Found {len(pdf_files)} PDFs for {game_dir.name}")
        for pdf in pdf_files:
            category = categorize_pdf(pdf)
            pdf_tasks.append((game_dir.name, category, pdf))

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_pdf, conn_pool, game, category, pdf): pdf
            for game, category, pdf in pdf_tasks
        }
        for future in concurrent.futures.as_completed(futures):
            pdf = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.error(f"Failed to process {pdf.name}: {e}")
                    

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

    conn_pool = create_connection_pool()

    conn = conn_pool.getconn()
    setup_database(conn)
    conn_pool.putconn(conn)

    chunk_data_slates(dest, conn_pool)
    conn_pool.closeall()

if __name__ == "__main__":
    main()