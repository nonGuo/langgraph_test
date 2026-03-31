"""
知识库检索工具 (基于 FAISS).

从本地知识库检索测试用例规范和 SQL 范例，用于指导 SQL 生成.

支持功能:
1. 文档导入和向量化
2. 基于语义的相似度检索
3. 支持分数阈值过滤
4. 批量检索
5. 知识库持久化

使用方式:
    ```python
    from tools.knowledge_tool import KnowledgeTool

    # 初始化知识库工具
    tool = KnowledgeTool(
        collection_name="test_case_knowledge",
        persist_directory="./knowledge_base",
    )

    # 导入文档
    tool.add_documents(
        documents=["文档内容 1", "文档内容 2"],
        metadatas=[{"source": "doc1.md"}, {"source": "doc2.md"}],
    )

    # 检索
    result = tool.search(query="主键唯一性检查")
    print(result.content)
    ```
"""

import json
import logging
import os
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeResult:
    """知识库检索结果."""
    success: bool
    content: str = ""
    error: Optional[str] = None
    source_documents: list[dict[str, Any]] = field(default_factory=list)
    score: float = 0.0
    query: str = ""


@dataclass
class DocumentChunk:
    """文档片段."""
    content: str
    metadata: dict[str, Any]
    embedding: Optional[list[float]] = None


class KnowledgeTool:
    """
    基于 FAISS 的知识库检索工具.

    从知识库检索历史测试用例和 SQL 范例，用于指导当前测试用例的 SQL 编写.

    Attributes:
        collection_name: 知识库集合名称
        persist_directory: 持久化目录
        top_k: 返回结果数量
        score_threshold: 分数阈值
    """

    def __init__(
        self,
        collection_name: str = "test_case_knowledge",
        persist_directory: Optional[str] = None,
        top_k: int = 3,
        score_threshold: Optional[float] = 0.3,
        embedding_model: Optional[str] = None,
    ):
        """
        初始化知识库工具.

        Args:
            collection_name: 知识库集合名称
            persist_directory: 持久化目录，默认 ./knowledge_base
            top_k: 返回结果数量
            score_threshold: 分数阈值 (0-1 之间)
            embedding_model: 嵌入模型名称，默认使用 BGE-M3
        """
        self.collection_name = collection_name
        self.persist_directory = persist_directory or "./knowledge_base"
        self.top_k = top_k
        self.score_threshold = score_threshold or 0.3
        self.embedding_model_name = embedding_model or "BAAI/bge-m3"

        # 延迟初始化
        self._index = None
        self._embeddings = None
        self._chunks: list[DocumentChunk] = []
        self._initialized = False

        # 确保持久化目录存在
        os.makedirs(self.persist_directory, exist_ok=True)

    def _lazy_init(self):
        """延迟初始化 FAISS 索引和嵌入模型."""
        if self._initialized:
            return

        logger.info(f"初始化知识库：collection={self.collection_name}, persist_dir={self.persist_directory}")

        try:
            # 尝试加载已保存的索引
            index_path = self._get_index_path()
            if os.path.exists(index_path):
                self._load_index()
                logger.info(f"加载已有知识库：{self.collection_name}")
            else:
                # 创建新索引
                self._create_index()
                logger.info(f"创建新知识库：{self.collection_name}")

            self._initialized = True

        except Exception as e:
            logger.exception(f"知识库初始化失败：{e}")
            raise

    def _get_index_path(self) -> str:
        """获取索引文件路径."""
        return os.path.join(self.persist_directory, f"{self.collection_name}.pkl")

    def _get_metadata_path(self) -> str:
        """获取元数据文件路径."""
        return os.path.join(self.persist_directory, f"{self.collection_name}_meta.pkl")

    def _create_embeddings(self):
        """创建嵌入模型."""
        try:
            from langchain_community.embeddings import HuggingFaceBgeEmbeddings

            model_kwargs = {
                "device": "cpu",
                "model_kwargs": {"trust_remote_code": True},
            }

            encode_kwargs = {
                "normalize_embeddings": True,
                "show_progress_bar": False,
            }

            return HuggingFaceBgeEmbeddings(
                model_name=self.embedding_model_name,
                model_kwargs=model_kwargs,
                encode_kwargs=encode_kwargs,
            )
        except ImportError as e:
            logger.warning(f"无法加载嵌入模型：{e}，使用简化模式")
            return None

    def _create_index(self):
        """创建 FAISS 索引."""
        try:
            import faiss

            # 创建索引 (使用余弦相似度)
            embedding_dim = 768  # BGE-M3 的输出维度
            self._index = faiss.IndexFlatIP(embedding_dim)  # 内积索引 (用于余弦相似度)

        except ImportError as e:
            logger.error(f"缺少依赖：{e}，请运行 pip install faiss-cpu")
            raise

    def _load_index(self):
        """加载已保存的索引."""
        try:
            index_path = self._get_index_path()
            meta_path = self._get_metadata_path()

            if os.path.exists(index_path):
                import faiss
                with open(index_path, "rb") as f:
                    self._index = faiss.deserialize_index(f.read())

            if os.path.exists(meta_path):
                with open(meta_path, "rb") as f:
                    data = pickle.load(f)
                    self._chunks = data.get("chunks", [])
                    self.embedding_model_name = data.get("embedding_model", self.embedding_model_name)

            # 初始化嵌入模型
            self._embeddings = self._create_embeddings()

        except Exception as e:
            logger.exception(f"加载索引失败：{e}")
            # 失败后创建新索引
            self._create_index()
            self._chunks = []

    def _save_index(self):
        """保存索引到磁盘."""
        try:
            index_path = self._get_index_path()
            meta_path = self._get_metadata_path()

            import faiss

            # 保存索引
            with open(index_path, "wb") as f:
                f.write(faiss.serialize_index(self._index))

            # 保存元数据
            with open(meta_path, "wb") as f:
                pickle.dump({
                    "chunks": self._chunks,
                    "embedding_model": self.embedding_model_name,
                }, f)

            logger.info(f"知识库已保存：{index_path}")

        except Exception as e:
            logger.exception(f"保存索引失败：{e}")

    def _embed_text(self, text: str) -> list[float]:
        """将文本转换为向量."""
        if self._embeddings is None:
            self._embeddings = self._create_embeddings()

        if self._embeddings:
            embedding = self._embeddings.embed_query(text)
            return embedding

        # 简化模式：使用 TF-IDF 或其他简单方法
        # 这里返回一个零向量作为占位符
        return [0.0] * 768

    def _split_text(self, text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]:
        """分割文本为片段."""
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", "。", "!", "!", ".", " ", ""],
        )

        return splitter.split_text(text)

    def add_documents(
        self,
        documents: list[str],
        metadatas: Optional[list[dict[str, Any]]] = None,
        ids: Optional[list[str]] = None,
    ) -> int:
        """
        添加文档到知识库.

        自动进行文本分割和向量化.

        Args:
            documents: 文档内容列表
            metadatas: 文档元数据列表 (与 documents 一一对应)
            ids: 文档 ID 列表 (与 documents 一一对应)，如不提供则自动生成

        Returns:
            添加的文档片段数量
        """
        self._lazy_init()

        if metadatas is None:
            metadatas = [{} for _ in documents]
        if ids is None:
            import hashlib
            ids = [f"doc_{i}_{hashlib.md5(doc.encode()).hexdigest()[:8]}" for i, doc in enumerate(documents)]

        # 文本分割
        all_chunks = []
        all_metadatas = []
        all_ids = []

        for i, (doc, meta, doc_id) in enumerate(zip(documents, metadatas, ids)):
            chunks = self._split_text(doc)
            for j, chunk in enumerate(chunks):
                all_chunks.append(chunk)
                all_metadatas.append({
                    **meta,
                    "chunk_index": j,
                    "total_chunks": len(chunks),
                    "doc_id": doc_id,
                })
                all_ids.append(f"{doc_id}_chunk_{j}")

        if not all_chunks:
            logger.warning("没有文档需要添加 (可能文档太短或被过滤)")
            return 0

        # 向量化并添加到索引
        embeddings = []
        for chunk in all_chunks:
            embedding = self._embed_text(chunk)
            embeddings.append(embedding)

            # 创建 DocumentChunk 对象
            self._chunks.append(DocumentChunk(
                content=chunk,
                metadata=all_metadatas[len(embeddings) - 1],
            ))

        # 添加到 FAISS 索引
        import numpy as np
        embedding_array = np.array(embeddings, dtype=np.float32)
        self._index.add(embedding_array)

        logger.info(f"添加 {len(all_chunks)} 个文档片段到知识库")

        # 保存索引
        self._save_index()

        return len(all_chunks)

    def add_documents_from_files(
        self,
        file_paths: list[str],
        metadata_template: Optional[dict[str, Any]] = None,
    ) -> int:
        """
        从文件添加文档到知识库.

        支持 Markdown, TXT, PDF 等格式.

        Args:
            file_paths: 文件路径列表
            metadata_template: 元数据模板，会添加到每个文档

        Returns:
            添加的文档片段数量
        """
        documents = []
        metadatas = []

        for file_path in file_paths:
            content = self._read_file(file_path)
            if content:
                documents.append(content)
                meta = {"source": file_path, "filename": Path(file_path).name}
                if metadata_template:
                    meta.update(metadata_template)
                metadatas.append(meta)
                logger.info(f"读取文件：{file_path} ({len(content)} chars)")

        return self.add_documents(documents, metadatas)

    def _read_file(self, file_path: str) -> str:
        """读取文件内容."""
        path = Path(file_path)
        if not path.exists():
            logger.error(f"文件不存在：{file_path}")
            return ""

        try:
            # Markdown 和 TXT
            if path.suffix.lower() in [".md", ".txt", ".text", ".sql"]:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()

            # PDF (需要 pypdf 库)
            elif path.suffix.lower() == ".pdf":
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(str(path))
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text()
                    return text
                except ImportError:
                    logger.warning("读取 PDF 需要安装 pypdf: pip install pypdf")
                    return ""

            # DOCX (需要 python-docx 库)
            elif path.suffix.lower() == ".docx":
                try:
                    from docx import Document
                    doc = Document(str(path))
                    return "\n".join([p.text for p in doc.paragraphs])
                except ImportError:
                    logger.warning("读取 DOCX 需要安装 python-docx: pip install python-docx")
                    return ""

            else:
                # 默认尝试读取为文本
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()

        except Exception as e:
            logger.exception(f"读取文件失败：{file_path}: {e}")
            return ""

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        filter_metadata: Optional[dict[str, Any]] = None,
    ) -> KnowledgeResult:
        """
        搜索知识库.

        Args:
            query: 搜索查询词
            top_k: 返回结果数量，默认使用 self.top_k
            score_threshold: 分数阈值，默认使用 self.score_threshold
            filter_metadata: 元数据过滤条件 (目前不支持)

        Returns:
            KnowledgeResult 检索结果
        """
        self._lazy_init()

        actual_top_k = top_k or self.top_k
        actual_threshold = score_threshold or self.score_threshold

        logger.info(f"检索知识库：query='{query[:50]}...', top_k={actual_top_k}")

        try:
            # 向量化查询
            query_embedding = self._embed_text(query)

            # 执行相似度搜索
            import numpy as np
            query_array = np.array([query_embedding], dtype=np.float32)

            # FAISS 搜索 (返回内积分数，对于归一化向量等价于余弦相似度)
            scores, indices = self._index.search(query_array, actual_top_k * 2)

            # 解析结果
            filtered_results = []

            for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
                if idx < 0 or idx >= len(self._chunks):
                    continue

                chunk = self._chunks[idx]

                # 应用分数阈值
                if score >= actual_threshold:
                    filtered_results.append({
                        "content": chunk.content,
                        "metadata": chunk.metadata,
                        "score": float(score),
                    })

            # 按分数排序
            filtered_results.sort(key=lambda x: x["score"], reverse=True)
            filtered_results = filtered_results[:actual_top_k]

            if not filtered_results:
                return KnowledgeResult(
                    success=True,
                    content="未找到相关的知识库文档 (可能内容不相关或分数低于阈值)",
                    query=query,
                    score=0.0,
                )

            # 构建返回内容
            content_parts = []
            source_docs = []

            for i, result in enumerate(filtered_results, 1):
                content = result["content"]
                score = result["score"]
                meta = result["metadata"]
                source = meta.get("source", "Unknown")
                filename = meta.get("filename", "Unknown")

                content_parts.append(
                    f"【相关文档 {i}: {filename}】(相关度：{score:.2f})\n{content}"
                )

                source_docs.append({
                    "filename": filename,
                    "source": source,
                    "content": content,
                    "score": score,
                })

            final_content = "\n\n---\n\n".join(content_parts)

            return KnowledgeResult(
                success=True,
                content=final_content,
                source_documents=source_docs,
                score=filtered_results[0]["score"] if filtered_results else 0.0,
                query=query,
            )

        except Exception as e:
            logger.exception(f"知识库检索异常：{e}")
            return KnowledgeResult(
                success=False,
                error=f"检索异常：{str(e)}",
                query=query,
            )

    def retrieve_few_shot(
        self,
        test_case_item: dict[str, Any],
    ) -> str:
        """
        为测试用例检索 few-shot SQL 示例.

        便捷方法，从测试用例中提取关键词并检索.

        Args:
            test_case_item: 测试用例字典，包含 case_name, tags, eval_step_descri

        Returns:
            检索到的 SQL 示例字符串
        """
        case_name = test_case_item.get("case_name", "")
        tags = test_case_item.get("tags", "")
        eval_step = test_case_item.get("eval_step_descri", "")

        # 构建组合查询词
        search_query = f"{case_name} {tags} {eval_step}".strip()

        logger.info(f"为测试用例检索 few-shot: {case_name[:50]}...")

        result = self.search(query=search_query, top_k=3)

        if result.success and result.content and "未找到" not in result.content:
            return result.content
        else:
            logger.warning(
                f"未找到相关 SQL 示例：{case_name}, "
                f"error={result.error or 'N/A'}"
            )
            return "未找到可参考的业务逻辑或 SQL"

    def batch_search(
        self,
        queries: list[str],
    ) -> list[KnowledgeResult]:
        """
        批量检索知识库.

        Args:
            queries: 查询词列表

        Returns:
            KnowledgeResult 列表
        """
        results = []
        for query in queries:
            results.append(self.search(query))
        return results

    def get_collection_stats(self) -> dict[str, Any]:
        """
        获取知识库统计信息.

        Returns:
            包含文档数量等信息的字典
        """
        self._lazy_init()

        return {
            "collection_name": self.collection_name,
            "total_documents": len(self._chunks),
            "persist_directory": self.persist_directory,
            "index_size": self._index.ntotal if self._index else 0,
        }

    def clear(self):
        """清空知识库 (谨慎使用)."""
        self._lazy_init()
        self._index = None
        self._chunks = []
        self._create_index()

        # 删除持久化文件
        index_path = self._get_index_path()
        meta_path = self._get_metadata_path()

        if os.path.exists(index_path):
            os.remove(index_path)
        if os.path.exists(meta_path):
            os.remove(meta_path)

        logger.info(f"知识库已清空：{self.collection_name}")


# ============================================================================
# LangChain 工具包装器
# ============================================================================

def create_knowledge_tool(knowledge_tool_instance: Optional[KnowledgeTool] = None):
    """
    创建 LangChain 工具.

    用于在 ReAct Agent 中使用知识库检索功能.

    Args:
        knowledge_tool_instance: KnowledgeTool 实例

    Returns:
        LangChain 工具函数
    """
    from langchain_core.tools import tool

    if knowledge_tool_instance is None:
        knowledge_tool_instance = KnowledgeTool()

    @tool("query_knowledge_base")
    def query_knowledge_base(
        test_case_name: str,
        search_query: Optional[str] = None
    ) -> str:
        """
        从知识库检索测试用例 SQL 范例.

        根据测试用例名称或自定义查询词，从知识库检索相似的历史测试用例和 SQL 范例.
        用于指导当前测试用例的 SQL 编写.

        Args:
            test_case_name: 测试用例名称（主要检索关键词）
            search_query: 可选的自定义查询词，如果提供则优先使用

        Returns:
            检索到的 SQL 范例和业务逻辑说明
        """
        try:
            # 优先使用自定义查询词
            query = search_query or test_case_name

            logger.info(f"检索知识库：test_case={test_case_name[:50]}...")

            result = knowledge_tool_instance.search(query=query)

            if result.success:
                output_lines = [
                    f"✅ 检索成功",
                    f"相关文档：{len(result.source_documents)} 篇",
                    f"相关度分数：{result.score:.2f}",
                    "\n检索到的内容:",
                    result.content,
                ]
                return "\n".join(output_lines)
            else:
                return f"❌ 检索失败：{result.error}"

        except Exception as e:
            logger.exception("Knowledge retrieval failed")
            return f"❌ 异常：{str(e)}"

    return query_knowledge_base


# ============================================================================
# 初始化脚本 (用于快速导入文档)
# ============================================================================

def init_knowledge_base(
    collection_name: str = "test_case_knowledge",
    persist_directory: str = "./knowledge_base",
    document_files: Optional[list[str]] = None,
):
    """
    初始化知识库并导入文档.

    便捷函数，用于首次设置知识库.

    Args:
        collection_name: 知识库集合名称
        persist_directory: 持久化目录
        document_files: 要导入的文档文件路径列表

    Returns:
        KnowledgeTool 实例
    """
    tool = KnowledgeTool(
        collection_name=collection_name,
        persist_directory=persist_directory,
    )

    if document_files:
        count = tool.add_documents_from_files(document_files)
        logger.info(f"成功导入 {count} 个文档片段")

        stats = tool.get_collection_stats()
        logger.info(f"知识库统计：{stats}")

    return tool
