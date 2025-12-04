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
import concurrent.futures
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
DEFAULT_MODEL = "all-MiniLM-L6-v2"
DEFAULT_BATCH_SIZE = 100

VOXCAST = {
    'init': f"{Sigil.GOLD}++AWAKENING++{Sigil.RESET} The Epistolary channels the Immaterium. {Sigil.GREEN}For the Lion!{Sigil.RESET}",
    'model_loaded': "Psychic conduit established: {model} on {device}",
    'no_chunks': "No unembedded fragments remain. The Librarius is complete.",
    'batch_start': "Channeling warp energies for {count} fragments...",
    'batch_complete': "Inscribed {count} soul-marks into the vault.",
    'finished': f"{Sigil.GOLD}++RITUAL COMPLETE++{Sigil.RESET} All fragments have been sanctified. {Sigil.GREEN}Praise the Omnissiah!{Sigil.RESET}",
    'progress': "Progress: {embedded}/{total} fragments embedded ({percent:.1f}%)",
    'exception': "Distrubance in the warp detected.. {exception}",
    'pool_created': "Cogitator link established to vault '{dbname}'",
    'db_fail': f"{Sigil.RED}++CORRUPTION DETECTED++{Sigil.RESET} Heretical taint in database rites: {{error}}",
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


def get_unembedded_chunks(conn, batch_size: int = 100) -> list:
    cursor = conn.cursor()
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


def embed_data_slates(model, conn_pool):
    
    chunk = get_unembedded_chunks()
    ids = [c[0] for c in chunks]
    texts = [prefix + c[1] for c in chunks]

    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    updates = [
        (format_pgvector(emb), chunk_id)
        for emb, chunk_id in zip(embeddings, ids)
    ]

def main():
    model = load_model('intfloat/multilingual-e5-large-instruct', 'cuda')

    
    conn_pool = create_connection_pool()

    embed_data_slates(conn_pool, model)
    conn_pool.closeall()

    logger.info(VOXCAST['finished'])

if __name__ == "__main__":
    main()