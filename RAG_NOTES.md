# Notes on RAG Systems, and Optimization methods

This doc tracks some notes as I reasearch more and learn about RAG architectures and implementation patterns. 

## Notes from Chapter 6 of "AI Engineering" by Chip Huyen

implement elasticsearch for wh40k odcuments and compare it to the retrieval methods for RAG

implement a cache for retriever to reduce latency

vector search algorithm, experiment with different ones like Inverted File Index, what does pgvector use?
alternative vector databases?

Experiment with evaluation set of queries and documents annotate relevance then compute precision, MLFlow tracking?

"Hybrid Search" combine term-based and semantic search algorithms to rerank results. reciprocal rank fusion (RRF)

Chunking play with size, overlap and tokenizers

my medatada of 'game' and 'codex/core/misc' was a good contextual retrieval pattern. should implement more of this like 'faction' to improve retrieval

augment chunk with LLM summary to prepend to chunk before embedding
