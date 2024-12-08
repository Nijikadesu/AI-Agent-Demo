"""Util that calls Arxiv."""
import os
from typing import Any, Iterator, List, Optional
import arxiv
from langchain_core.documents import Document


class ArxivAPIWrapper:
    """Wrapper around ArxivAPI.

    To use, you should have the ``arxiv_tools`` python package installed.
    https://lukasschwab.me/arxiv.py/index.html
    This wrapper will use the Arxiv API to conduct searches and
    fetch document summaries. By default, it will return the document summaries
    of the top-k results.
    If the query is in the form of arxiv_tools identifier
    (see https://info.arxiv.org/help/find/index.html), it will return the paper
    corresponding to the arxiv_tools identifier.
    It limits the Document content by doc_content_chars_max.
    Set doc_content_chars_max=None if you don't want to limit the content size.

    Attributes:
        top_k_results: number of the top-scored document used for the arxiv_tools tool
        ARXIV_MAX_QUERY_LENGTH: the cut limit on the query used for the arxiv_tools tool.
        continue_on_failure (bool): If True, continue loading other URLs on failure.
        load_max_docs: a limit to the number of loaded documents
        load_all_available_meta:
            if True: the `metadata` of the loaded Documents contains all available
            meta info (see https://lukasschwab.me/arxiv.py/index.html#Result),
            if False: the `metadata` contains only the published date, title,
            authors and summary.
        doc_content_chars_max: an optional cut limit for the length of a document's
            content

    Example:
        .. code-block:: python

            from langchain_community.utilities.arxiv_tools import ArxivAPIWrapper
            arxiv_tools = ArxivAPIWrapper(
                top_k_results = 3,
                ARXIV_MAX_QUERY_LENGTH = 300,
                load_max_docs = 3,
                load_all_available_meta = False,
                doc_content_chars_max = 40000
            )
            arxiv_tools.run("tree of thought llm")
    """

    arxiv_search = arxiv.Search
    arxiv_exceptions = (
        arxiv.ArxivError,
        arxiv.UnexpectedEmptyPageError,
        arxiv.HTTPError,
    )
    top_k_results: int = 3
    ARXIV_MAX_QUERY_LENGTH: int = 300
    continue_on_failure: bool = False
    load_max_docs: int = 500
    load_all_available_meta: bool = True
    doc_content_chars_max: Optional[int] = 40000

    client = arxiv.Client()

    def _fetch_results(self, query: str) -> Any:
        """Helper function to fetch arxiv_tools results based on query."""
        search = self.arxiv_search(
            query[: self.ARXIV_MAX_QUERY_LENGTH],
            max_results=self.top_k_results
        )
        return self.client.results(search)

    def get_summaries_as_docs(self, query: str) -> List[Document]:
        """
        Performs an arxiv_tools search and returns list of
        documents, with summaries as the content.

        If an error occurs or no documents found, error text
        is returned instead. Wrapper for
        https://lukasschwab.me/arxiv.py/index.html#Search

        Args:
            query: a plaintext search query
        """
        try:
            results = self._fetch_results(
                query
            )  # Using helper function to fetch results
        except self.arxiv_exceptions as ex:
            return [Document(page_content=f"Arxiv exception: {ex}")]
        docs = [
            Document(
                page_content=result.summary,
                metadata={
                    "Entry ID": result.entry_id,
                    "Published": result.updated.date(),
                    "Title": result.title,
                    "Authors": ", ".join(a.name for a in result.authors),
                },
            )
            for result in results
        ]
        return docs

    def run(self, query: str) -> str:
        """
        Performs an arxiv_tools search and A single string
        with the publish date, title, authors, and summary
        for each article separated by two newlines.

        If an error occurs or no documents found, error text
        is returned instead. Wrapper for
        https://lukasschwab.me/arxiv.py/index.html#Search

        Args:
            query: a plaintext search query
        """
        try:
            results = self._fetch_results(
                query
            )  # Using helper function to fetch results
        except self.arxiv_exceptions as ex:
            return f"Arxiv exception: {ex}"
        docs = [
            f"Published: {result.updated.date()}\n"
            f"Title: {result.title}\n"
            f"Authors: {', '.join(a.name for a in result.authors)}\n"
            f"Summary: {result.summary}"
            for result in results
        ]
        if docs:
            return "\n\n".join(docs)[: self.doc_content_chars_max]
        else:
            return "No good Arxiv Result was found"

    def load(self, query: str) -> List[Document]:
        """
        Run Arxiv search and get the article texts plus the article meta information.
        See https://lukasschwab.me/arxiv.py/index.html#Search

        Returns: a list of documents with the document.page_content in text format

        Performs an arxiv_tools search, downloads the top k results as PDFs, loads
        them as Documents, and returns them in a List.

        Args:
            query: a plaintext search query
        """
        return list(self.lazy_load(query))

    def lazy_load(self, query: str) -> Iterator[Document]:
        """
        Run Arxiv search and get the article texts plus the article meta information.
        See https://lukasschwab.me/arxiv.py/index.html#Search

        Returns: documents with the document.page_content in text format

        Performs an arxiv_tools search, downloads the top k results as PDFs, loads
        them as Documents, and returns them.

        Args:
            query: a plaintext search query
        """
        try:
            import fitz
        except ImportError:
            raise ImportError(
                "PyMuPDF package not found, please install it with "
                "`pip install pymupdf`"
            )

        # Remove the ":" and "-" from the query, as they can cause search problems
        query = query.replace(":", "").replace("-", "")
        results = self._fetch_results(
            query
        )  # Using helper function to fetch results

        for result in results:
            doc_file_name: str = result.download_pdf()
            with fitz.open(doc_file_name) as doc_file:
                text: str = "".join(page.get_text() for page in doc_file)

            if self.load_all_available_meta:
                extra_metadata = {
                    "entry_id": result.entry_id,
                    "published_first_time": str(result.published.date()),
                    "comment": result.comment,
                    "journal_ref": result.journal_ref,
                    "doi": result.doi,
                    "primary_category": result.primary_category,
                    "categories": result.categories,
                    "links": [link.href for link in result.links],
                }
            else:
                extra_metadata = {}
            metadata = {
                "Published": str(result.updated.date()),
                "Title": result.title,
                "Authors": ", ".join(a.name for a in result.authors),
                "Summary": result.summary,
                **extra_metadata,
            }
            yield Document(
                page_content=text[: self.doc_content_chars_max], metadata=metadata
            )
            os.remove(doc_file_name)


if __name__ == "__main__":
    arxiv_search = ArxivAPIWrapper()
    res = arxiv_search.get_summaries_as_docs("KAN")
    print(res)
    print(type(res))
    for r in res:
        print(r)