'''
Lexicanium - Initiate of the Librarius
    - Extracts sacred .zip archives into Data-Slates
    - Data-Slates are sanctified and loaded into the Cogitator vault
    - Summons the machine spirit of unstructured
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


class Sigil:
    GREEN = '\033[38;5;34m'
    GOLD = '\033[38;5;178m'
    RED = '\033[38;5;124m'
    RESET = '\033[0m'


logging.basicConfig(level=logging.INFO, format='[LIBRARIUS] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

VOXCAST = {
    'init': f"{Sigil.GOLD}++AWAKENING++{Sigil.RESET} The Lexicanium stirs from dormancy. {Sigil.GREEN}For the Lion!{Sigil.RESET}",
    'pool_created': "Cogitator link established to vault '{dbname}'",
    'db_ready': f"Sacred table '{{table}}' prepared. {Sigil.GREEN}The Machine Spirit is pleased.{Sigil.RESET}",
    'db_fail': f"{Sigil.RED}++CORRUPTION DETECTED++{Sigil.RESET} Heretical taint in database rites: {{error}}",
    'extract_success': "Data-Slate extracted: {path}",
    'extract_fail': f"{Sigil.RED}Extraction failure - possible Chaos taint: {{error}}{Sigil.RESET}",
    'extraction_complete': "Recovered {count} Data-Slates in {time:.2f} seconds.",
    'no_archives': "No sacred archives located in {source}. The hunt continues...",
    'pdf_found': "Auspex scan: {count} sacred texts in {game} sector",
    'pdf_skip': "Text '{name}' already inscribed ({count} fragments in vault)",
    'pdf_processing': "Sanctifying: {name} ({size:.1f} MB) - this may take a while...",
    'batch_insert': "{count} fragments committed to the Librarius",
    'batch_fail': f"{Sigil.RED}Inscription failure - consult the Watchers: {{error}}{Sigil.RESET}",
    'pdf_complete': f"Sanctified {{count}} fragments from {{name}}. {Sigil.GREEN}The Emperor Protects.{Sigil.RESET}",
    'pdf_fail': f"{Sigil.RED}Sanctification failed for {{name}}: {{error}}. Summon a Techmarine!{Sigil.RESET}",
    'creds_fail': f"{Sigil.RED}++ACCESS DENIED++{Sigil.RESET} Vault credentials corrupted. The Fallen must not learn our secrets!",
    'finished': f"{Sigil.GOLD}++RITUAL COMPLETE++{Sigil.RESET} The data-communion has ended. {Sigil.GREEN}Praise the Omnissiah!{Sigil.RESET}"
}

DEFAULT_ARCHIVE_DIR = Path("./archive")
DEFAULT_DESTINATION = Path("./Data-Slates")
DEFAULT_PG_CREDS = Path("./pg-credentials.json")


def load_db_creds() -> dict:
    try:
        with open(DEFAULT_PG_CREDS, 'r') as json_creds:
            return json.load(json_creds)
    except Exception:
        logger.error(VOXCAST['creds_fail'])
        exit(1)


def create_connection_pool(min_conn: int = 2, max_conn: int = 10) -> pool.ThreadedConnectionPool:
    creds = load_db_creds()
    try:
        conn_pool = pool.ThreadedConnectionPool(min_conn, max_conn, **creds)
        logger.info(VOXCAST['pool_created'].format(dbname=creds.get('dbname')))
        return conn_pool
    except Exception as e:
        logger.error(VOXCAST['db_fail'].format(error=e))
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
        cursor.execute("""CREATE INDEX IF NOT EXISTS idx_chunks_source_file ON chunks(source_file);""")
        conn.commit()
        logger.info(VOXCAST['db_ready'].format(table=table_name))
    except Exception as e:
        logger.error(VOXCAST['db_fail'].format(error=e))
        conn.rollback()
    finally:
        cursor.close()


def extract_zip(filepath: Path, destination: Path) -> bool:
    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            zf.extractall(destination)
        return True
    except Exception as e:
        logger.error(VOXCAST['extract_fail'].format(error=e))
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
                logger.info(VOXCAST['extract_success'].format(path=data))
            except Exception as e:
                logger.error(VOXCAST['extract_fail'].format(error=e))
    return extracted


def get_chunk_count(conn, source_file: str) -> int:
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM chunks WHERE source_file = %s",
            (source_file,)
        )
        return cursor.fetchone()[0]
    finally:
        cursor.close()


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
        logger.info(VOXCAST['batch_insert'].format(count=len(chunks)))
    except Exception as e:
        logger.error(VOXCAST['batch_fail'].format(error=e))
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


def process_pdf(conn_pool: pool.ThreadedConnectionPool, game: str, category: str, pdf: Path):
    conn = conn_pool.getconn()
    try:
        existing_count = get_chunk_count(conn, pdf.name)
        if existing_count > 0:
            logger.info(VOXCAST['pdf_skip'].format(name=pdf.name, count=existing_count))
            return
    finally:
        conn_pool.putconn(conn)

    file_size_mb = pdf.stat().st_size / (1024 * 1024)
    logger.info(VOXCAST['pdf_processing'].format(name=pdf.name, size=file_size_mb))
    start = time.perf_counter()
    elements = partition_pdf(str(pdf))
    elapsed = time.perf_counter() - start
    logger.info(f"Parsed {pdf.name} in {elapsed:.1f}s - extracted {len(elements)} elements")
    chunks = [
        (game, category, pdf.name, i, str(el), type(el).__name__)
        for i, el in enumerate(elements)
    ]

    conn = conn_pool.getconn()
    try:
        insert_chunks_batch(conn, chunks)
        logger.info(VOXCAST['pdf_complete'].format(count=len(elements), name=pdf.name))
    finally:
        conn_pool.putconn(conn)


def chunk_data_slates(dest: Path, conn_pool: pool.ThreadedConnectionPool, max_workers: int = 4):
    directories = [d for d in dest.iterdir() if d.is_dir()]

    pdf_tasks = []
    for game_dir in directories:
        pdf_files = list(game_dir.glob("*.pdf"))
        logger.info(VOXCAST['pdf_found'].format(count=len(pdf_files), game=game_dir.name))
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
                logger.error(VOXCAST['pdf_fail'].format(name=pdf.name, error=e))


@click.command()
@click.option('--source', '-s', type=click.Path(exists=True, path_type=Path),
              default=DEFAULT_ARCHIVE_DIR, help='Directory containing zip files')
@click.option('--dest', '-d', type=click.Path(path_type=Path),
              default=DEFAULT_DESTINATION, help='Destination directory for extraction')
@click.option('--skip-extract', is_flag=True, help='Skip zip extraction, process existing Data-Slates only')
def main(source: Path, dest: Path, skip_extract: bool) -> None:
    """Extract zip files from archive directory into Data-Slates."""
    dest.mkdir(parents=True, exist_ok=True)

    logger.info(VOXCAST['init'])

    if not skip_extract:
        zip_paths = list(source.glob("*.zip"))
        if not zip_paths:
            logger.warning(VOXCAST['no_archives'].format(source=source))
            return

        start_time = time.perf_counter()
        extracted = proc_load_from_archive(zip_paths, dest)
        elapsed = time.perf_counter() - start_time
        logger.info(VOXCAST['extraction_complete'].format(count=len(extracted), time=elapsed))

    conn_pool = create_connection_pool()

    conn = conn_pool.getconn()
    setup_database(conn)
    conn_pool.putconn(conn)

    chunk_data_slates(dest, conn_pool)
    conn_pool.closeall()

    logger.info(VOXCAST['finished'])

if __name__ == "__main__":
    main()