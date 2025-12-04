'''
Epistolary - Astropath of the Librarius
    - Consume sanctified records transcribed by the Lexicanium
    - Creates vector embeddings of unstructured PDF data in postgresql db
    - Stores result in pgvector Vector column
'''

from pathlib import Path
from psycopg2 import pool
from psycopg2.extras import execute_values
from sentence_transformers import SentenceTransformer
import click
import json
import logging
import numpy as np
import queue
import threading

class Sigil:
    GREEN = '\033[38;5;34m'
    GOLD = '\033[38;5;178m'
    RED = '\033[38;5;124m'
    RESET = '\033[0m'

logging.basicConfig(level=logging.INFO, format='[LIBRARIUS] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_PG_CREDS = Path("./pg-credentials.json")
DEFAULT_MODEL = "intfloat/multilingual-e5-large-instruct"
DEFAULT_DEVICE = "cuda"
DEFAULT_BATCH_SIZE = 100

VOXCAST = {
    'init': f"{Sigil.GOLD}++AWAKENING++{Sigil.RESET} The Epistolary channels the Immaterium. {Sigil.GREEN}For the Lion!{Sigil.RESET}",
    'model_loaded': "Psychic conduit established: {model} on {device}",
    'no_chunks': "No unembedded fragments remain. The Librarius is complete.",
    'batch_start': "Channeling warp energies for {count} fragments...",
    'batch_complete': "Inscribed {count} soul-marks into the vault.",
    'finished': f"{Sigil.GOLD}++RITUAL COMPLETE++{Sigil.RESET} All fragments have been sanctified. {Sigil.GREEN}Praise the Omnissiah!{Sigil.RESET}",
    'progress': "Progress: {embedded}/{total} fragments embedded ({percent:.1f}%)",
    'exception': "Disturbance in the warp detected.. {exception}",
    'pool_created': "Cogitator link established to vault '{dbname}'",
    'db_fail': f"{Sigil.RED}++CORRUPTION DETECTED++{Sigil.RESET} Heretical taint in database rites: {{error}}",
    'creds_fail': f"{Sigil.RED}++SEAL BROKEN++{Sigil.RESET} The sacred credentials have been lost to the void.",
    'filter_active': "Watchers performing filtration rites: {col} = '{val}'.",
    'catalogus_header': f"{Sigil.GOLD}++CATALOGUS QUERY++{Sigil.RESET} Distinct values within column '{{column}}':",
    'catalogus_item': "  * {val}",
    'close_conn': "Severing noospheric link. We are blind to the warp."
}


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


def get_unembedded_chunks(conn, batch_size: int, filter_col: str | None, filter_val: str | None) -> list:
    cursor = conn.cursor()
    if filter_col and filter_val:
        cursor.execute(f"""
            SELECT id, content
            FROM chunks
            WHERE embedding IS NULL
            AND "{filter_col}" = %s
            ORDER BY id
            LIMIT %s
        """, (filter_val, batch_size))
    else:
        cursor.execute("""
            SELECT id, content
            FROM chunks
            WHERE embedding IS NULL
            ORDER BY id
            LIMIT %s
        """, (batch_size,))
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_unembedded_count(conn, filter_col: str | None, filter_val: str | None) -> int:
    cursor = conn.cursor()
    if filter_col and filter_val:
        cursor.execute(f"""
            SELECT COUNT(*) FROM chunks
            WHERE embedding IS NULL AND "{filter_col}" = %s
        """, (filter_val,))
    else:
        cursor.execute("SELECT COUNT(*) FROM chunks WHERE embedding IS NULL")
    count = cursor.fetchone()[0]
    cursor.close()
    return count


def get_distinct_values(conn, column: str) -> list:
    """Get distinct values for a column to help user pick a filter."""
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT DISTINCT "{column}"
        FROM chunks
        WHERE embedding IS NULL
        ORDER BY "{column}"
    """)
    values = [row[0] for row in cursor.fetchall()]
    cursor.close()
    return values


def update_embeddings(conn, updates: list[tuple]):
    cursor = conn.cursor()
    try:
        execute_values(
            cursor,
            """
            UPDATE chunks 
            SET embedding = data.embedding::vector
            FROM (VALUES %s) AS data(embedding, id)
            WHERE chunks.id = data.id
            """,
            updates,
            template="(%s, %s)"
        )
        conn.commit()
        logger.info(VOXCAST['batch_complete'].format(count=len(updates)))
    except Exception as e:
        logger.error(VOXCAST['db_fail'].format(error = e))
    cursor.close()


def load_model(model_name: str, device: str):
    try:
        model = SentenceTransformer(model_name, device=device)
        logger.info(VOXCAST['model_loaded'])
        return model
    except Exception as e:
        logger.error(VOXCAST['exception'].format(exception = e))
        return None


def format_pgvector(embedding: np.ndarray) -> str:
    return '[' + ','.join(map(str, embedding.tolist())) + ']'


def db_writer_worker(conn_pool: pool.ThreadedConnectionPool, write_queue: queue.Queue, stop_event: threading.Event):
    while not stop_event.is_set() or not write_queue.empty():
        try:
            updates = write_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        conn = conn_pool.getconn()
        try:
            update_embeddings(conn, updates)
        finally:
            conn_pool.putconn(conn)
            write_queue.task_done()


def embed_data_slates(model, conn_pool, batch_size: int, filter_col: str | None, filter_val: str | None):
    conn = conn_pool.getconn()
    try:
        total_to_embed = get_unembedded_count(conn, filter_col, filter_val)
    finally:
        conn_pool.putconn(conn)

    if total_to_embed == 0:
        logger.info(VOXCAST['no_chunks'])
        return 0

    write_queue = queue.Queue(maxsize=2)
    stop_event = threading.Event()

    writer_thread = threading.Thread(
        target=db_writer_worker,
        args=(conn_pool, write_queue, stop_event),
        daemon=True
    )
    writer_thread.start()

    total_embedded = 0

    while True:
        conn = conn_pool.getconn()
        try:
            chunks = get_unembedded_chunks(conn, batch_size, filter_col, filter_val)
        finally:
            conn_pool.putconn(conn)

        if not chunks:
            break

        ids = [c[0] for c in chunks]
        texts = [c[1] for c in chunks]

        logger.info(VOXCAST['batch_start'].format(count=len(chunks)))

        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

        updates = [
            (format_pgvector(emb), chunk_id)
            for emb, chunk_id in zip(embeddings, ids)
        ]

        write_queue.put(updates)

        total_embedded += len(chunks)
        percent = (total_embedded / total_to_embed) * 100
        logger.info(VOXCAST['progress'].format(
            embedded=total_embedded,
            total=total_to_embed,
            percent=percent
        ))

    stop_event.set()
    writer_thread.join()

    return total_embedded


@click.command()
@click.option('--filter-col', '-c', default=None, help='Column to filter on (e.g., "game")')
@click.option('--filter-val', '-v', default=None, help='Value to filter for')
@click.option('--list-values', '-l', default=None, help='List distinct values for a column and exit')
@click.option('--batch-size', '-b', default=DEFAULT_BATCH_SIZE, help='Batch size for embedding')
@click.option('--device', '-d', default=DEFAULT_DEVICE, help='Device to run model on (cuda/cpu)')
def main(filter_col: str, filter_val: str, list_values: str, batch_size: int, device: str):
    conn_pool = create_connection_pool()

    if list_values:
        conn = conn_pool.getconn()
        try:
            values = get_distinct_values(conn, list_values)
            click.echo(VOXCAST['catalogus_header'].format(column=list_values))
            for val in values:
                click.echo(VOXCAST['catalogus_item'].format(val=val))
        finally:
            conn_pool.putconn(conn)
            logger.info(VOXCAST['close_conn'])
            conn_pool.closeall()
        return

    logger.info(VOXCAST['init'])

    if filter_col and filter_val:
        logger.info(VOXCAST['filter_active'].format(col=filter_col, val=filter_val))

    model = load_model(DEFAULT_MODEL, device)
    if model is None:
        return

    try:
        embed_data_slates(model, conn_pool, batch_size, filter_col, filter_val)
    finally:
        logger.info(VOXCAST['close_conn'])
        conn_pool.closeall()

    logger.info(VOXCAST['finished'])


if __name__ == "__main__":
    main()