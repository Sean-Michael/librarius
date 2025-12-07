'''
Codicier - Oracle of the Librarius
 - Embeds a user query
 - Queries pgvector for top-k similar results
 - Stuff retrieved chunks + question into a prompt, get answer
'''

from pathlib import Path
from psycopg2 import pool
from sentence_transformers import SentenceTransformer
import click
import json
import logging
import numpy as np

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


VOXCAST = {
    'init': f"{Sigil.GOLD}++AWAKENING++{Sigil.RESET} The Codicier channels the Immaterium. {Sigil.GREEN}For the Lion!{Sigil.RESET}",
    'model_loaded': "Psychic conduit established: {model} on {device}",
    'embed_complete': "Query transcribed into the warp. Consulting the Librarius...",
    'finished': f"{Sigil.GOLD}++RITUAL COMPLETE++{Sigil.RESET} All fragments have been sanctified. {Sigil.GREEN}Praise the Omnissiah!{Sigil.RESET}",
    'exception': "Disturbance in the warp detected.. {exception}",
    'pool_created': "Cogitator link established to vault '{dbname}'",
    'db_fail': f"{Sigil.RED}++CORRUPTION DETECTED++{Sigil.RESET} Heretical taint in database rites: {{error}}",
    'creds_fail': f"{Sigil.RED}++SEAL BROKEN++{Sigil.RESET} The sacred credentials have been lost to the void.",
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
        logger.info(VOXCAST['model_loaded'].format(model=model_name,device=device))
        return model
    except Exception as e:
        logger.error(VOXCAST['exception'].format(exception = e))
        return None


def get_k_nearest(embedded_query, conn, game):
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT content, embedding <-> %s AS distance
            FROM chunks
            WHERE game = %s
            ORDER BY distance
            LIMIT 5
        """, (embedded_query,game))
    except Exception as e:
        logger.error(VOXCAST['exception'].format(exception=e))
    k_nearest=cursor.fetchall()
    return k_nearest


def format_pgvector(embedding: np.ndarray) -> str:
    return '[' + ','.join(map(str, embedding.tolist())) + ']'


def interactive_mode(model, conn, game):
    while True:
        try:
            query = input(f"\n{Sigil.GOLD}[QUERY]{Sigil.RESET} Enter query (or 'q' to quit): ").strip()
            if not query:
                continue
            if query.lower() in ('quit', 'exit', 'q'):
                break
            embed_user_query(query, model, conn, game)
        except KeyboardInterrupt:
            print()
            break


def embed_user_query(user_query, model, conn, game):

    try:
        embedded_query = model.encode(user_query, normalize_embeddings=True, show_progress_bar=True)
        logger.info(VOXCAST['embed_complete'])
        formatted_embed_query = format_pgvector(embedded_query)
        print(get_k_nearest(formatted_embed_query, conn, game))
            
    except Exception as e:
        logger.error(VOXCAST['exception'].format(exception=e))
        return False 


@click.command()
@click.option('--model_name', '-m', default=DEFAULT_MODEL, help='Model to run embedding with')
@click.option('--device', '-d', default=DEFAULT_DEVICE, help='Device to run model on (cuda/cpu)')
@click.option('--game', '-g', default=None, help='Filter results to a particular game (30k, 40k, Killteam2)')
@click.argument('query', required=False)
def main(model_name: str, device: str, query: str, game: str):
    conn_pool = create_connection_pool()
    conn = conn_pool.getconn()

    logger.info(VOXCAST['init'])

    model = load_model(model_name, device)
    if model is None:
        return

    try:
        if query:
            embed_user_query(query, model, conn, game)
        else:
            interactive_mode(model, conn, game)
    finally:
        logger.info(VOXCAST['close_conn'])
        conn_pool.closeall()

    logger.info(VOXCAST['finished'])


if __name__ == "__main__":
    main()