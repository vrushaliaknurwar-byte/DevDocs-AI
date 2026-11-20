import time
import logging
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types
from google.genai.errors import APIError
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class GeminiService:
    def __init__(
        self,
        api_key: Optional[str] = None,
        embedding_model: Optional[str] = None,
        generation_model: Optional[str] = None,
        dimensions: Optional[int] = None
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        if not self.api_key:
            logger.warning("GEMINI_API_KEY is not configured! Gemini API calls will fail.")

        self.embedding_model = embedding_model or settings.EMBEDDING_MODEL
        self.generation_model = generation_model or settings.GENERATION_MODEL
        self.dimensions = dimensions or settings.EMBEDDING_DIMENSIONS
        self._client: Optional[genai.Client] = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            if not self.api_key:
                raise ValueError("GEMINI_API_KEY is not set. Please provide it in .env")
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def get_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for a single string."""
        vectors = self.get_embeddings_batch([text])
        if not vectors:
            raise RuntimeError("Gemini failed to return embedding for text")
        return vectors[0]

    def get_embeddings_batch(self, texts: List[str], batch_size: int = 25) -> List[List[float]]:
        """
        Generate embedding vectors for a batch of strings.
        Splits into chunks of batch_size to stay within API payload limits.
        """
        if not texts:
            return []

        all_embeddings: List[List[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            # Replace empty text with a placeholder to avoid empty content errors
            cleaned_batch = [t if t.strip() else "# empty" for t in batch]

            retries = 3
            delay = 1.0
            last_err = None

            for attempt in range(retries):
                try:
                    resp = self.client.models.embed_content(
                        model=self.embedding_model,
                        contents=cleaned_batch,
                        config=types.EmbedContentConfig(output_dimensionality=self.dimensions)
                    )
                    batch_vectors = [list(e.values) for e in resp.embeddings]
                    all_embeddings.extend(batch_vectors)
                    break
                except APIError as e:
                    last_err = e
                    logger.warning(
                        f"Gemini embed_content API error (attempt {attempt+1}/{retries}): {e}"
                    )
                    if attempt < retries - 1:
                        time.sleep(delay)
                        delay *= 2
                except Exception as e:
                    last_err = e
                    logger.error(f"Unexpected error in get_embeddings_batch: {e}")
                    if attempt < retries - 1:
                        time.sleep(delay)
                        delay *= 2

            else:
                raise RuntimeError(f"Failed to generate embeddings after {retries} retries: {last_err}")

        return all_embeddings

    def generate_answer(self, question: str, context_chunks: List[Dict[str, Any]]) -> str:
        """
        Generate an answer to a question using the retrieved code chunks as context.
        """
        # Format context
        context_parts = []
        for idx, chunk in enumerate(context_chunks, start=1):
            file_path = chunk.get("file_path", "unknown")
            start_line = chunk.get("start_line", 1)
            end_line = chunk.get("end_line", 1)
            code_text = chunk.get("code_text", "")
            context_parts.append(
                f"--- Code Snippet #{idx} ---\n"
                f"File: {file_path} (Lines {start_line}-{end_line})\n"
                f"```\n{code_text}\n```"
            )

        context_str = "\n\n".join(context_parts) if context_parts else "No relevant code snippets found."

        prompt = (
            "You are DevDocs AI, an expert code comprehension assistant. "
            "Your task is to answer questions about a codebase using only the provided code context snippets.\n\n"
            "Guidelines:\n"
            "1. Base your answer strictly on the provided code snippets.\n"
            "2. When explaining, clearly reference the file names and functions or classes involved.\n"
            "3. If the provided snippets do not contain enough information to answer the question, clearly state that the answer cannot be determined from the indexed code.\n"
            "4. Be concise, precise, and directly address what was asked.\n\n"
            f"Code Context:\n{context_str}\n\n"
            f"Question:\n{question}\n\n"
            "Answer:"
        )

        candidate_models = [self.generation_model, "gemini-3.5-flash", "gemini-3.8-flash"]
        # Deduplicate candidate models
        seen = set()
        models_to_try = [m for m in candidate_models if not (m in seen or seen.add(m))]

        last_err = None
        for model_name in models_to_try:
            try:
                resp = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                if resp.text:
                    return resp.text.strip()
            except APIError as e:
                last_err = e
                logger.warning(f"Generation failed on model {model_name}: {e}. Trying fallback if available.")
            except Exception as e:
                last_err = e
                logger.warning(f"Error on model {model_name}: {e}. Trying fallback if available.")

        raise RuntimeError(f"Failed to generate answer from Gemini API: {last_err}")


# Global singleton instance
gemini_service = GeminiService()
