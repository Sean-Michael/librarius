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
import ollama

class Sigil:
    GREEN = '\033[38;5;34m'
    GOLD = '\033[38;5;178m'
    RED = '\033[38;5;124m'
    RESET = '\033[0m'

logging.basicConfig(level=logging.INFO, format='[LIBRARIUS] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_PG_CREDS = Path("./pg-credentials.json")
DEFAULT_EMBED_MODEL = "intfloat/multilingual-e5-large-instruct"
DEFAULT_CHAT_MODEL = "mistral:7b"
DEFAULT_DEVICE = "cpu"


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


def load_model(embed_model_name: str, device: str):
    try:
        model = SentenceTransformer(embed_model_name, device=device)
        logger.info(VOXCAST['model_loaded'].format(model=embed_model_name,device=device))
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


def interactive_mode(embed_model, chat_model_name: str, conn, game: str):
    history = []
    print(f"\n{Sigil.GOLD}++CHAT MODE ACTIVATED++{Sigil.RESET}")
    print(f"Using chat model: {Sigil.GREEN}{chat_model_name}{Sigil.RESET}")
    print("Commands: 'q' to quit, 'clear' to reset conversation history\n")

    while True:
        try:
            query = input(f"{Sigil.GOLD}[YOU]{Sigil.RESET} ").strip()
            if not query:
                continue
            if query.lower() in ('quit', 'exit', 'q'):
                break
            if query.lower() == 'clear':
                history = []
                print(f"{Sigil.GREEN}Conversation history cleared.{Sigil.RESET}\n")
                continue

            response, history = query_with_rag(
                query, embed_model, chat_model_name, conn, game, history
            )

            if response:
                print(f"\n{Sigil.GREEN}[CODICIER]{Sigil.RESET} {response}\n")
            else:
                print(f"\n{Sigil.RED}[ERROR]{Sigil.RESET} Failed to get response from the LLM.\n")

        except KeyboardInterrupt:
            print()
            break


def embed_and_retrieve(user_query: str, model, conn, game: str) -> list:
    try:
        embedded_query = model.encode(user_query, normalize_embeddings=True, show_progress_bar=False)
        logger.info(VOXCAST['embed_complete'])
        formatted_embed_query = format_pgvector(embedded_query)
        chunks = get_k_nearest(formatted_embed_query, conn, game)
        return chunks
    except Exception as e:
        logger.error(VOXCAST['exception'].format(exception=e))
        return []


def query_with_rag(user_query: str, embed_model, chat_model_name: str,
                   conn, game: str, history: list | None = None) -> tuple:
    chunks = embed_and_retrieve(user_query, embed_model, conn, game)

    if not chunks:
        return "No relevant context found in the Librarius.", history or []

    response, new_history = chat_with_chunks(chat_model_name, user_query, chunks, history)
    return response, new_history 


def build_rag_prompt(query: str, chunks: list) -> str:
    context = "\n\n".join([f"[Chunk {i+1}] (distance: {dist:.4f})\n{content}"
                          for i, (content, dist) in enumerate(chunks)])
    return f"""You are a knowledgeable assistant for tabletop gaming rules. Use the following retrieved context to answer the user's question. If the context doesn't contain relevant information, say so clearly.

RETRIEVED CONTEXT:
{context}

USER QUESTION: {query}

Provide a clear, accurate answer based on the context above."""


def chat_with_chunks(model_name: str, query: str, chunks: list, history: list | None = None) -> tuple:
    if history is None:
        history = []

    rag_prompt = build_rag_prompt(query, chunks)

    messages = history + [{"role": "user", "content": rag_prompt}]

    try:
        response = ollama.chat(model=model_name, messages=messages)
        assistant_message = response['message']['content']

        new_history = history + [
            {"role": "user", "content": query},
            {"role": "assistant", "content": assistant_message}
        ]
        return assistant_message, new_history
    except Exception as e:
        logger.error(VOXCAST['exception'].format(exception=e))
        return None, history


@click.command()
@click.option('--embed_model_name', '-e', default=DEFAULT_EMBED_MODEL, help='Model to run embedding with')
@click.option('--chat_model_name', '-c', default=DEFAULT_CHAT_MODEL, help='Ollama model for chat responses')
@click.option('--device', '-d', default=DEFAULT_DEVICE, help='Device to run model on (cuda/cpu)')
@click.option('--game', '-g', default=None, help='Filter results to a particular game (30k, 40k, Killteam2)')
@click.argument('query', required=False)
def main(embed_model_name: str, chat_model_name: str, device: str, query: str, game: str):
    conn_pool = create_connection_pool()
    conn = conn_pool.getconn()

    logger.info(VOXCAST['init'])

    embed_model = load_model(embed_model_name, device)
    if embed_model is None:
        return

    try:
        if query:
            response, _ = query_with_rag(query, embed_model, chat_model_name, conn, game)
            if response:
                print(f"\n{Sigil.GREEN}[CODICIER]{Sigil.RESET} {response}\n")
        else:
            interactive_mode(embed_model, chat_model_name, conn, game)
    finally:
        logger.info(VOXCAST['close_conn'])
        conn_pool.closeall()

    logger.info(VOXCAST['finished'])


if __name__ == "__main__":
    main()