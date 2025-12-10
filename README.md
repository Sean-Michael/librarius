```ascii
 _     _________________  ___  ______ _____ _   _ _____ 
| |   |_   _| ___ \ ___ \/ _ \ | ___ \_   _| | | /  ___|
| |     | | | |_/ / |_/ / /_\ \| |_/ / | | | | | \ `--. 
| |     | | | ___ \    /|  _  ||    /  | | | | | |`--. \
| |_____| |_| |_/ / |\ \| | | || |\ \ _| |_| |_| /\__/ /
\_____/\___/\____/\_| \_\_| |_/\_| \_|\___/ \___/\____/ 
```

> "A Librarium or Librarius is the command and communications centre of a Space Marine Chapter's fortress-monastery, and the repository for centuries of wisdom and history, culled from the reports, treatises and memoirs of the chapter's greatest warriors and finest minds." - [Lexicanum](https://wh40k.lexicanum.com/wiki/Librarium) 

Just as Codex Astartes chapters rely on their Librarian order to maintain records, we will use  [Retrieval Augmented Generation (RAG)](https://arxiv.org/pdf/2005.11401) to give LLMs an understanding of the rules for Warhammer 40k!

This can enable agents or chatbots to interact with prompts or other tools in a way that is grounded in reality of the rules as written. This reduces hallucinations and improves response quality.

### Project Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1. Data Ingestion | PDF extraction, chunking, storage | Complete |
| 2. Embedding | Vector embeddings via SentenceTransformers | Complete |
| 3. Retrieval & Generation | Query embedding, retrieval, LLM chat | Complete |

## RAG Pipeline

These steps outline the process of taking raw PDFs from .zip archives, processing, and transforming them into vector embeddings ready for retreival by LLMs.


### 1. Data Ingestion and Pre-Processing

This is the first step in the chain. Since we are gathering information from PDFs, we need to account for the varying levels of quality and formatting. 

#### Lexicanium

Our python application [lexicanium](lexicanium.py) finds `.zip` archives, extracts their contents into `Data-Slates` and then begins preprocessing by attempting to categorize PDFs into one of three distinctions:
- Rule Book - Universal and gameplay rules for all factions, universe lore.
- Codex - Faction specific rules, unit composition specifications, faction lore.
- Misc. - Everything else, errata, addendums

This is done rather naivly through a simple filename matching logic. 

```python3
def categorize_pdf(pdf: Path) -> str:
    name = pdf.name.lower()
    if 'rules' in name or 'core' in name:
        return "rules"
    elif 'codex' in name:
        return "codices"
    return "misc"
```

##### UPDATE: 

This is actually no longer the case and I've instead opted for creating a rigid templatized filename schema if you will that is enforced strictly. The loss in flexibility of naming is made up for by the gains of adding more metadata easily.

| Metadata | Source | Example Values |
|----------|--------|----------------|
| `faction` | Filename prefix | `dark_angels`, `space_marines`, `orks`, `loyalist_legiones` |
| `edition` | Filename middle | `5th`, `9th`, `10th`, `2nd` |
| `category` | Filename suffix | `codex`, `rules`, `liber`, `expansion`, `errata` |
| `game` | Parent directory | `40k`, `30k`, `Killteam2` |

The filename pattern is enforced via regex: `{faction}_{edition}_{category}.pdf`

```python
# Expected filename pattern: faction_edition_type.pdf
# Examples: dark_angels_10th_codex.pdf, space_marines_9th_rules.pdf, loyalist_legiones_2nd_liber.pdf
FILENAME_PATTERN = re.compile(r'^(?P<faction>.+)_(?P<edition>\d+(?:st|nd|rd|th))_(?P<type>\w+)\.pdf$', re.IGNORECASE)
```

It adds some additional labor to no longer being able to just drag and drop zips or pdfs into `Data-Slates` but it is well worth it to hopefully improve the retrieval system.

This will get saved when the PDF is processed further into partitions.

 For partitioning the PDFs into smaller bite-sized 'chunks' it utilizes the `unstructured` library, writing to a PostgreSQL database hosted on [Caliban.](https://github.com/Sean-Michael/home-kubernetes-cloud) in batches for speed. 
 
 Native PDFs (I'm not sure the proper term) have their text and whatnot nicely formatted and encoded in a way that is much easier to parse, the challenge comes from the image based PDFs which are usually scans or photos of the rulebooks and codices, etc. These require some Computer Vision models that can perform [Optical Character Recognition (OCR).](https://en.wikipedia.org/wiki/Optical_character_recognition) The unstructured library does some logic to determine how to handle the PDFs and calls [tesseract-ocr](https://github.com/tesseract-ocr/tesseract?tab=readme-ov-file) which is an open source OCR engine. 

#### Database chunks Table Schema

The chunks are inserted into the database with the following table schema which provides useful metadata for embedding and retrieval later.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `SERIAL PRIMARY KEY` | Auto-incrementing ID |
| `game` | `VARCHAR(100)` | Game system name (directory name) |
| `category` | `VARCHAR(50)` | PDF category: `rules`, `codices`, or `misc` |
| `source_file` | `VARCHAR(500)` | Original PDF filename |
| `chunk_index` | `INTEGER` | Position of chunk within the PDF |
| `content` | `TEXT` | Extracted text content |
| `element_type` | `VARCHAR(100)` | Unstructured element type (e.g., `NarrativeText`, `Title`) |
| `embedding` | `VECTOR(1536)` | embedding vector (pgvector) |
| `created_at` | `TIMESTAMP` | Auto-set insertion timestamp |

You will notice that we included the `embedding` column but haven't processed any embeddings yet. On to the next step!

#### Semantic Chunking

The standard chunking approach outlined above represents my first pass at the architecutre. After reading more online and in the excellent book "AI Engineering" by Chip Huyen, I learned about the different patterns we could impelemnt to improve performance. Flattening all PDF elements into a single text stream and splitting by character count as we were previously doing leaves much room for improvement. As we saw in the initial retrievals I felt like the system was missing a significant portion of the content that could be used to answer user queries. Game rules are inherently structuredk, they usually follow a pattern of turns and "phases", weapon and unit profiles often are part of distinct and cohesive tables. Splitting up these units that are designed to be together can remove valuable and necessary context. In order to remedy this we needed a more 'semantic' appraoch to chunking.

The `--semantic` flag enables hierarchical chunking that preserves this structure:

```bash
python lexicanium.py --skip-extract --semantic
```

This writes to a separate `semantic_chunks` table with additional columns for A/B testing against the original approach:

| Column | Type | Description |
|--------|------|-------------|
| `section_hierarchy` | `TEXT[]` | Breadcrumb trail of section headers (e.g., `['Combat', 'Attack Rolls']`) |
| `page_number` | `INTEGER` | Source page for citations back to the original tome |
| `is_table` | `BOOLEAN` | Flags data tables (weapon profiles, point costs, etc.) |
| `parent_chunk_id` | `INTEGER` | Foreign key for parent-child chunk relationships |

Key differences in semantic mode:
- **Section-aware splitting**: Title/Header elements from `unstructured` define chunk boundaries. Content stays grouped under its heading.
- **Table preservation**: Tables are extracted as standalone chunks with their headers intact, preventing stat blocks from getting mangled (hopefully).
- **Hierarchy tracking**: Each chunk knows which section it belongs to, enabling queries like "find all chunks under Combat Rules".



### 2. Embedding

Now that we have chunks in the database, we need to create vector embeddings for semantic search.

#### Epistolary

The [epistolary](epistolary.py) script loads a SentenceTransformer model and embeds all unembedded chunks in the database. It uses `intfloat/multilingual-e5-large-instruct` by default which produces 1024-dimensional embeddings.

The script processes chunks in batches and uses a separate writer thread to keep the GPU busy while database writes happen in the background.

```bash
# embed all unembedded chunks
python epistolary.py

# filter to a specific game system
python epistolary.py --filter-col game --filter-val "40k"

# list available values for a column
python epistolary.py --list-values game

# embed the semantic_chunks table instead
python epistolary.py --table semantic_chunks
```

You can also specify `--device cpu` if you don't have a CUDA capable device like a GPU, though it may slower.

### 3. Retrieval & Generation

With embeddings in place, we can now query the Librarius.

#### Codicier

The [codicier](codicier.py) script embeds a user query using the same model, performs a k-nearest-neighbors search against pgvector, and stuffs the retrieved chunks into a prompt for an LLM. It uses Ollama for local inference.

```bash
# single query
python codicier.py --game "40k" "What are the rules for overwatch?"

# interactive chat mode (omit the query argument)
python codicier.py --game "40k"

# query the semantic_chunks table for richer context
python codicier.py --game "40k" --table semantic_chunks
```

The `--game` flag filters retrieval to chunks from a specific game system, which helps anchor responses in the correct ruleset. In interactive mode you can type `clear` to reset conversation history or `q` to quit.

When querying `semantic_chunks`, retrieved context includes section hierarchy and page numbers, giving the LLM better grounding for its responses and enabling it to cite specific pages.