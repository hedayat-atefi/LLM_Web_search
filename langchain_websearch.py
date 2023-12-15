import os
from typing import List
import concurrent.futures

from langchain.document_loaders.unstructured import UnstructuredFileLoader
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import FAISS
from langchain.retrievers.document_compressors.embeddings_filter import EmbeddingsFilter
from langchain.retrievers import ContextualCompressionRetriever
from langchain.schema import Document


class MyUnstructuredHTMLLoader(UnstructuredFileLoader):
    """Loader that uses unstructured to download and load HTML content from
       an URL."""

    def _get_elements(self) -> List:
        from unstructured.partition.html import partition_html
        # Note the hack: We assume that self.file_path is in fact a URL
        return partition_html(url=self.file_path, **self.unstructured_kwargs)


def pretty_print_docs(docs):
    print(
        f"\n{'-' * 100}\n".join(
            [f"Document {i+1} ({d.metadata['source']}):\n\n" + d.page_content for i, d in enumerate(docs)]
        )
    )


def docs_to_pretty_str(docs) -> str:
    ret_str = ""
    for i, doc in enumerate(docs):
        ret_str += f"Result {i+1}:\n"
        ret_str += f"{doc.page_content}\n"
        ret_str += f"Source URL: {doc.metadata['source']}\n\n"
    return ret_str


def load_url(url: str):
    return MyUnstructuredHTMLLoader(url).load()


def faiss_embedding_query_urls(query: str, url_list: list[str], num_results: int = 5,
                               similarity_threshold: float = 0.5) -> list[Document]:
    documents = []
    #for url in url_list:
    #    documents.extend(MyUnstructuredHTMLLoader(url).load())

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(load_url, url): url for url in url_list}
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                documents.extend(future.result())
            except Exception as exc:
                print('%r generated an exception: %s' % (url, exc))

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
    texts = text_splitter.split_documents(documents)
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    retriever = FAISS.from_documents(texts, embeddings).as_retriever(
        search_kwargs={"k": num_results}
    )

    embeddings_filter = EmbeddingsFilter(embeddings=embeddings, k=None, similarity_threshold=similarity_threshold)
    compression_retriever = ContextualCompressionRetriever(base_compressor=embeddings_filter, base_retriever=retriever)

    compressed_docs = compression_retriever.get_relevant_documents(query)
    return compressed_docs
