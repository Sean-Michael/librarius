'''
Codicier - _ of the Librarius
 - Embeds a user query
 - Queries pgvector for top-k similar results
 - Stuff retrieved chunks + question into a prompt, get answer
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


def load_model(model_name: str, device: str):
    try:
        model = SentenceTransformer(model_name, device=device)
        logger.info(VOXCAST['model_loaded'])
        return model
    except Exception as e:
        logger.error(VOXCAST['exception'].format(exception = e))
        return None


@click.command()
@click.option('--model_name', '-m', default=DEFAULT_MODEL, help='Model to run embedding with')
@click.option('--device', '-d', default=DEFAULT_DEVICE, help='Device to run model on (cuda/cpu)')
def main(model_name: str, device: str):
    conn_pool = create_connection_pool()

    conn = conn_pool.getconn()

    logger.info(VOXCAST['init'])

    model = load_model(model_name, device)
    if model is None:
        return

    try:
        pass
    finally:
        logger.info(VOXCAST['close_conn'])
        conn_pool.closeall()

    logger.info(VOXCAST['finished'])


if __name__ == "__main__":
    main()