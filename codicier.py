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
DEFAULT_DEVICE = "cuda"
DEFAULT_TABLE = "chunks"
DEFAULT_TOP_K = 10


VOXCAST = {
    'init': f"{Sigil.GOLD}++AWAKENING++{Sigil.RESET} The Codicier channels the Immaterium. {Sigil.GREEN}For the Lion!{Sigil.RESET}",
    'model_loaded': "Psychic conduit established: {model} on {device}",
    'embed_complete': "Query transcribed into the warp. Consulting the Librarius...",
    'finished': f"{Sigil.GOLD}++RITUAL COMPLETE++{Sigil.RESET} All fragments have been sanctified. {Sigil.GREEN}Praise the Omnissiah!{Sigil.RESET}",
    'exception': "Disturbance in the warp detected.. {exception}",
    'pool_created': "Cogitator link established to vault '{dbname}'",
    'db_fail': f"{Sigil.RED}++CORRUPTION DETECTED++{Sigil.RESET} Heretical taint in database rites: {{error}}",
    'creds_fail': f"{Sigil.RED}++SEAL BROKEN++{Sigil.RESET} The sacred credentials have been lost to the void.",
    'close_conn': "Severing noospheric link. We are blind to the warp.",
    'retrieval_header': f"{Sigil.GOLD}++RETRIEVAL RESULTS++{Sigil.RESET} Found {{count}} fragments:",
    'retrieval_chunk': "  [{i}] dist={dist:.4f} | {source} | {faction} | {section}",
    'retrieval_chunk_basic': "  [{i}] dist={dist:.4f} | {source}",
    'filter_active': "Filtering: game={game}, faction={faction}",
    'no_filter': "No filters applied - searching all records",
    'verbose_chunk_header': f"{Sigil.GOLD}++VERBOSE CHUNK {{i}}++{Sigil.RESET}",
}


def normalize_faction(faction: str | None) -> str | None:
    if faction is None:
        return None
    return faction.replace('_', ' ').lower()


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


def get_k_nearest(embedded_query, conn, game: str | None, faction: str | None,
                  table_name: str = DEFAULT_TABLE, top_k: int = DEFAULT_TOP_K):
    cursor = conn.cursor()
    is_semantic = table_name == "semantic_chunks"

    faction = normalize_faction(faction)

    conditions = ["embedding IS NOT NULL"]
    params = [embedded_query]

    if game:
        conditions.append("game = %s")
        params.append(game)
    if faction:
        conditions.append("faction = %s")
        params.append(faction)

    where_clause = " AND ".join(conditions)
    params.append(top_k)

    if game or faction:
        logger.info(VOXCAST['filter_active'].format(
            game=game or 'any',
            faction=faction or 'any'
        ))
    else:
        logger.info(VOXCAST['no_filter'])

    try:
        if is_semantic:
            cursor.execute(f"""
                SELECT content, embedding <-> %s AS distance,
                       section_hierarchy, page_number, element_type,
                       source_file, faction
                FROM "{table_name}"
                WHERE {where_clause}
                ORDER BY distance
                LIMIT %s
            """, params)
        else:
            cursor.execute(f"""
                SELECT content, embedding <-> %s AS distance,
                       source_file, faction
                FROM "{table_name}"
                WHERE {where_clause}
                ORDER BY distance
                LIMIT %s
            """, params)
    except Exception as e:
        logger.error(VOXCAST['exception'].format(exception=e))
        return [], is_semantic

    k_nearest = cursor.fetchall()

    logger.info(VOXCAST['retrieval_header'].format(count=len(k_nearest)))
    for i, row in enumerate(k_nearest):
        if is_semantic:
            content, dist, hierarchy, page, elem_type, source, fac = row
            section = " > ".join(hierarchy) if hierarchy else "?"
            logger.info(VOXCAST['retrieval_chunk'].format(
                i=i+1, dist=dist, source=source, faction=fac, section=section[:50]
            ))
        else:
            content, dist, source, fac = row
            logger.info(VOXCAST['retrieval_chunk_basic'].format(
                i=i+1, dist=dist, source=source
            ))

    return k_nearest, is_semantic


def format_pgvector(embedding: np.ndarray) -> str:
    return '[' + ','.join(map(str, embedding.tolist())) + ']'


def print_verbose_chunks(chunks: list, is_semantic: bool) -> None:
    print(f"\n{Sigil.GOLD}++RETRIEVED CHUNKS++{Sigil.RESET}")
    print("=" * 80)

    for i, row in enumerate(chunks):
        if is_semantic:
            content, dist, hierarchy, page, elem_type, source, faction = row
            section = " > ".join(hierarchy) if hierarchy else "Unknown"
            page_str = f"p.{page}" if page else "?"
            print(f"\n{Sigil.GOLD}[Chunk {i+1}]{Sigil.RESET} dist={Sigil.GREEN}{dist:.4f}{Sigil.RESET}")
            print(f"  Source: {source}")
            print(f"  Faction: {faction} | Type: {elem_type} | Page: {page_str}")
            print(f"  Section: {section}")
            print(f"  {'-' * 40}")
            print(f"  {content[:500]}{'...' if len(content) > 500 else ''}")
        else:
            content, dist, source, faction = row
            print(f"\n{Sigil.GOLD}[Chunk {i+1}]{Sigil.RESET} dist={Sigil.GREEN}{dist:.4f}{Sigil.RESET}")
            print(f"  Source: {source}")
            print(f"  Faction: {faction}")
            print(f"  {'-' * 40}")
            print(f"  {content[:500]}{'...' if len(content) > 500 else ''}")

    print("\n" + "=" * 80)


def interactive_mode(embed_model, chat_model_name: str, conn, game: str | None,
                     faction: str | None, table_name: str = DEFAULT_TABLE,
                     top_k: int = DEFAULT_TOP_K, verbose: bool = False):
    history = []
    print(f"\n{Sigil.GOLD}++CHAT MODE ACTIVATED++{Sigil.RESET}")
    print(f"Using chat model: {Sigil.GREEN}{chat_model_name}{Sigil.RESET}")
    print(f"Querying table: {Sigil.GREEN}{table_name}{Sigil.RESET}")
    print(f"Filters: game={Sigil.GREEN}{game or 'any'}{Sigil.RESET}, faction={Sigil.GREEN}{faction or 'any'}{Sigil.RESET}")
    print(f"Retrieving top {Sigil.GREEN}{top_k}{Sigil.RESET} chunks per query")
    print(f"Verbose mode: {Sigil.GREEN}{'ON' if verbose else 'OFF'}{Sigil.RESET}")
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
                query, embed_model, chat_model_name, conn, game, faction, table_name, top_k, history, verbose
            )

            if response:
                print(f"\n{Sigil.GREEN}[CODICIER]{Sigil.RESET} {response}\n")
            else:
                print(f"\n{Sigil.RED}[ERROR]{Sigil.RESET} Failed to get response from the LLM.\n")

        except KeyboardInterrupt:
            print()
            break


def embed_and_retrieve(user_query: str, model, conn, game: str | None,
                       faction: str | None, table_name: str = DEFAULT_TABLE,
                       top_k: int = DEFAULT_TOP_K, verbose: bool = False) -> tuple[list, bool]:
    try:
        embedded_query = model.encode("query: " + user_query, normalize_embeddings=True, show_progress_bar=False)
        logger.info(VOXCAST['embed_complete'])
        formatted_embed_query = format_pgvector(embedded_query)
        chunks, is_semantic = get_k_nearest(formatted_embed_query, conn, game, faction, table_name, top_k)
        if verbose and chunks:
            print_verbose_chunks(chunks, is_semantic)
        return chunks, is_semantic
    except Exception as e:
        logger.error(VOXCAST['exception'].format(exception=e))
        return [], False


def query_with_rag(user_query: str, embed_model, chat_model_name: str,
                   conn, game: str | None, faction: str | None,
                   table_name: str = DEFAULT_TABLE, top_k: int = DEFAULT_TOP_K,
                   history: list | None = None, verbose: bool = False) -> tuple:
    chunks, is_semantic = embed_and_retrieve(user_query, embed_model, conn, game, faction, table_name, top_k, verbose)

    if not chunks:
        return "No relevant context found in the Librarius.", history or []

    response, new_history = chat_with_chunks(chat_model_name, user_query, chunks, is_semantic, history)
    return response, new_history 


def build_rag_prompt(query: str, chunks: list, is_semantic: bool = False) -> str:
    if is_semantic:
        context_parts = []
        for i, (content, dist, hierarchy, page, elem_type, source, faction) in enumerate(chunks):
            section = " > ".join(hierarchy) if hierarchy else "Unknown"
            page_str = f"p.{page}" if page else "?"
            context_parts.append(
                f"[Chunk {i+1}] ({elem_type}, {page_str}, {faction}, distance: {dist:.4f})\n"
                f"Source: {source}\nSection: {section}\n{content}"
            )
        context = "\n\n".join(context_parts)
    else:
        context = "\n\n".join([f"[Chunk {i+1}] ({faction}, distance: {dist:.4f})\n"
                              f"Source: {source}\n{content}"
                              for i, (content, dist, source, faction) in enumerate(chunks)])

    return f"""You are a knowledgeable assistant for tabletop gaming rules. Use the following retrieved context to answer the user's question. If the context doesn't contain relevant information, say so clearly.

RETRIEVED CONTEXT:
{context}

USER QUESTION: {query}

Provide a clear, accurate answer based on the context above."""


def chat_with_chunks(model_name: str, query: str, chunks: list,
                     is_semantic: bool = False, history: list | None = None) -> tuple:
    if history is None:
        history = []

    rag_prompt = build_rag_prompt(query, chunks, is_semantic)

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
@click.option('--faction', '-f', default=None, help='Filter results to a specific faction (e.g., "space marines", "t\'au")')
@click.option('--table', '-t', default=DEFAULT_TABLE, help='Table to query (chunks or semantic_chunks)')
@click.option('--top-k', '-k', default=DEFAULT_TOP_K, help='Number of chunks to retrieve per query')
@click.option('--verbose', '-v', is_flag=True, help='Print retrieved chunks content (useful for debugging)')
@click.argument('query', required=False)
def main(embed_model_name: str, chat_model_name: str, device: str, query: str,
         game: str | None, faction: str | None, table: str, top_k: int, verbose: bool):
    conn_pool = create_connection_pool()
    conn = conn_pool.getconn()

    logger.info(VOXCAST['init'])

    embed_model = load_model(embed_model_name, device)
    if embed_model is None:
        return

    try:
        if query:
            response, _ = query_with_rag(query, embed_model, chat_model_name, conn, game, faction, table, top_k, None, verbose)
            if response:
                print(f"\n{Sigil.GREEN}[CODICIER]{Sigil.RESET} {response}\n")
        else:
            interactive_mode(embed_model, chat_model_name, conn, game, faction, table, top_k, verbose)
    finally:
        logger.info(VOXCAST['close_conn'])
        conn_pool.closeall()

    logger.info(VOXCAST['finished'])


if __name__ == "__main__":
    main()