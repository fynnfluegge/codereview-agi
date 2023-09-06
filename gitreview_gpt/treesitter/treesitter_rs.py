import tree_sitter
from gitreview_gpt.treesitter.treesitter import (
    Treesitter,
    TreesitterNode,
    get_source_from_node,
)
from gitreview_gpt.constants import Language
from gitreview_gpt.treesitter.treesitter_registry import TreesitterRegistry


class TreesitterRust(Treesitter):
    def __init__(self):
        super().__init__(Language.RUST)

    def parse(self, file_bytes: bytes) -> list[TreesitterNode]:
        super().parse(file_bytes)
        result = []
        methods = self._query_all_methods(self.tree.root_node)
        for method in methods:
            method_name = self._query_method_name(method["method"])
            doc_comment = method["doc_comment"]
            result.append(TreesitterNode(method_name, doc_comment, method["method"]))
        return result

    def _query_method_name(self, node: tree_sitter.Node):
        if node.type == "function_item":
            for child in node.children:
                if child.type == "identifier":
                    return child.text.decode()
        return None

    def _query_all_methods(self, node: tree_sitter.Node):
        methods = []
        if node.type == "function_item":
            doc_comment_nodes = []
            if (
                node.prev_named_sibling
                and node.prev_named_sibling.type == "line_comment"
            ):
                current_doc_comment_node = node.prev_named_sibling
                while (
                    current_doc_comment_node
                    and current_doc_comment_node.type == "line_comment"
                ):
                    doc_comment_nodes.append(
                        get_source_from_node(current_doc_comment_node)
                    )
                    if current_doc_comment_node.prev_named_sibling:
                        current_doc_comment_node = (
                            current_doc_comment_node.prev_named_sibling
                        )
                    else:
                        current_doc_comment_node = None

            doc_comment_str = ""
            doc_comment_nodes.reverse()
            for doc_comment_node in doc_comment_nodes:
                doc_comment_str += doc_comment_node + "\n"
            if doc_comment_str.strip() != "":
                methods.append({"method": node, "doc_comment": doc_comment_str.strip()})
            else:
                methods.append({"method": node, "doc_comment": None})
        else:
            for child in node.children:
                methods.extend(self._query_all_methods(child))
        return methods


# Register the TreesitterJava class in the registry
TreesitterRegistry.register_treesitter(Language.RUST, TreesitterRust)
