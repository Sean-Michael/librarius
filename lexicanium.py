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
from psycopg2 import pool, sql
import psycopg2.extras
import click
import json
import re

DEFAULT_CHUNK_SIZE = 4000
DEFAULT_CHUNK_OVERLAP = 800

# Expected filename pattern: faction_edition_type.pdf
# Examples: dark_angels_10th_codex.pdf, space_marines_9th_rules.pdf, loyalist_legiones_2nd_liber.pdf
FILENAME_PATTERN = re.compile(r'^(?P<faction>.+)_(?P<edition>\d+(?:st|nd|rd|th))_(?P<type>\w+)\.pdf$', re.IGNORECASE)

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
    'pdf_parsed': "Tome {name} decoded in {time:.1f}s - {count} runes extracted from the warp",
    'pdf_chunked': "Consolidated {count} sacred passages (sigil_size={size}, overlap={overlap})",
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
DEFAULT_TABLE = "chunks"


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


def setup_database(conn, table_name: str = DEFAULT_TABLE):
    cursor = conn.cursor()
    try:
        cursor.execute(sql.SQL("""
            CREATE TABLE IF NOT EXISTS {} (
                id SERIAL PRIMARY KEY,
                game VARCHAR(100),
                faction VARCHAR(100),
                edition VARCHAR(20),
                category VARCHAR(50),
                source_file VARCHAR(500),
                chunk_index INTEGER,
                content TEXT,
                element_type VARCHAR(100),
                embedding VECTOR(1536),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """).format(sql.Identifier(table_name)))
        conn.commit()

        index_name = "idx_%s_source_file" % table_name
        cursor.execute(sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} (source_file);").format(
            sql.Identifier(index_name),
            sql.Identifier(table_name)
        ))
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


def get_chunk_count(conn, source_file: str, table_name: str = DEFAULT_TABLE) -> int:
    cursor = conn.cursor()
    try:
        query = sql.SQL("SELECT COUNT(*) FROM {} WHERE source_file = %s").format(
            sql.Identifier(table_name)
        )
        cursor.execute(query, (source_file,))
        return cursor.fetchone()[0]
    finally:
        cursor.close()


def insert_chunks_batch(conn, chunks: list[tuple], table_name: str = DEFAULT_TABLE):
    cursor = conn.cursor()
    try:
        query = sql.SQL("""
            INSERT INTO {} (game, faction, edition, category, source_file, chunk_index, content, element_type)
            VALUES %s
        """).format(sql.Identifier(table_name))
        psycopg2.extras.execute_values(cursor, query, chunks, page_size=100)
        conn.commit()
        logger.info(VOXCAST['batch_insert'].format(count=len(chunks)))
    except Exception as e:
        logger.error(VOXCAST['batch_fail'].format(error=e))
        conn.rollback()
    finally:
        cursor.close()


def parse_pdf_filename(pdf: Path) -> dict:
    match = FILENAME_PATTERN.match(pdf.name)
    if not match:
        raise ValueError(
            f"Filename '{pdf.name}' does not match pattern 'faction_edition_type.pdf' "
            f"(e.g., dark_angels_10th_codex.pdf)"
        )
    return {
        'faction': match.group('faction').replace('_', ' ').lower(),
        'edition': match.group('edition').lower(),
        'category': match.group('type').lower()
    }


def chunk_elements(elements: list, chunk_size: int, chunk_overlap: int) -> list[str]:
    full_text = "\n\n".join(str(el) for el in elements)

    if len(full_text) <= chunk_size:
        return [full_text] if full_text.strip() else []

    chunks = []
    start = 0

    while start < len(full_text):
        end = start + chunk_size

        if end < len(full_text):
            break_point = full_text.rfind("\n\n", start + chunk_size // 2, end)
            if break_point != -1:
                end = break_point

        chunk = full_text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - chunk_overlap if end < len(full_text) else len(full_text)

    return chunks


def process_pdf(conn_pool: pool.ThreadedConnectionPool, game: str, pdf: Path,
                 table_name: str = DEFAULT_TABLE,
                 chunk_size: int = DEFAULT_CHUNK_SIZE,
                 chunk_overlap: int = DEFAULT_CHUNK_OVERLAP):
    metadata = parse_pdf_filename(pdf)

    conn = conn_pool.getconn()
    try:
        existing_count = get_chunk_count(conn, pdf.name, table_name)
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
    logger.info(VOXCAST['pdf_parsed'].format(name=pdf.name, time=elapsed, count=len(elements)))

    text_chunks = chunk_elements(elements, chunk_size, chunk_overlap)
    logger.info(VOXCAST['pdf_chunked'].format(count=len(text_chunks), size=chunk_size, overlap=chunk_overlap))

    chunks = [
        (game, metadata['faction'], metadata['edition'], metadata['category'],
         pdf.name, i, chunk_text, "combined_chunk")
        for i, chunk_text in enumerate(text_chunks)
    ]

    conn = conn_pool.getconn()
    try:
        insert_chunks_batch(conn, chunks, table_name)
        logger.info(VOXCAST['pdf_complete'].format(count=len(text_chunks), name=pdf.name))
    finally:
        conn_pool.putconn(conn)


def chunk_data_slates(dest: Path, conn_pool: pool.ThreadedConnectionPool,
                      table_name: str = DEFAULT_TABLE,
                      chunk_size: int = DEFAULT_CHUNK_SIZE,
                      chunk_overlap: int = DEFAULT_CHUNK_OVERLAP):
    directories = [d for d in dest.iterdir() if d.is_dir()]

    for game_dir in directories:
        pdf_files = list(game_dir.glob("*.pdf"))
        logger.info(VOXCAST['pdf_found'].format(count=len(pdf_files), game=game_dir.name))
        for pdf in pdf_files:
            try:
                process_pdf(conn_pool, game_dir.name, pdf, table_name, chunk_size, chunk_overlap)
            except Exception as e:
                logger.error(VOXCAST['pdf_fail'].format(name=pdf.name, error=e))


@click.command()
@click.option('--source', '-s', type=click.Path(exists=True, path_type=Path),
              default=DEFAULT_ARCHIVE_DIR, help='Directory containing zip files')
@click.option('--dest', '-d', type=click.Path(path_type=Path),
              default=DEFAULT_DESTINATION, help='Destination directory for extraction')
@click.option('--table', '-t', default=DEFAULT_TABLE,
              help='Table name for storing chunks in the vault')
@click.option('--chunk-size', '-c', type=int, default=DEFAULT_CHUNK_SIZE,
              help='Size of each sacred passage in characters')
@click.option('--chunk-overlap', '-o', type=int, default=DEFAULT_CHUNK_OVERLAP,
              help='Overlap between passages to preserve context')
@click.option('--skip-extract', is_flag=True, help='Skip zip extraction, process existing Data-Slates only')
def main(source: Path, dest: Path, table: str, chunk_size: int, chunk_overlap: int, skip_extract: bool) -> None:
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
    setup_database(conn, table)
    conn_pool.putconn(conn)

    chunk_data_slates(dest, conn_pool, table, chunk_size, chunk_overlap)
    conn_pool.closeall()

    logger.info(VOXCAST['finished'])

if __name__ == "__main__":
    main()