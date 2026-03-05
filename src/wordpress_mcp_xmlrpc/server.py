"""WordPress XML-RPC MCP Server.

Wraps all wp.* XML-RPC methods and exposes them as MCP tools returning JSON.
"""

import json
import os
import xmlrpc.client
from datetime import datetime

from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# WPClient
# ---------------------------------------------------------------------------

class WPClient:
    def __init__(self, url: str, username: str, password: str, blog_id: int = 1):
        endpoint = url.rstrip("/") + "/xmlrpc.php"
        self.server = xmlrpc.client.ServerProxy(endpoint, use_datetime=True)
        self.blog_id = blog_id
        self.username = username
        self.password = password

    def _resolve(self, method: str):
        """Resolve a dotted method name (e.g. 'wp.getPost') on the ServerProxy."""
        obj = self.server
        for part in method.split("."):
            obj = getattr(obj, part)
        return obj

    def call(self, method: str, *args):
        """Standard call: func(blog_id, username, password, *args)."""
        func = self._resolve(method)
        raw = func(self.blog_id, self.username, self.password, *args)
        return _compact(_strip_response(_to_json_safe(raw)))

    def call_page(self, method: str, page_id: int, *args):
        """Legacy page call: func(blog_id, page_id, username, password, *args).

        wp.getPage and wp.editPage put page_id before credentials.
        """
        func = self._resolve(method)
        raw = func(self.blog_id, page_id, self.username, self.password, *args)
        return _compact(_strip_response(_to_json_safe(raw)))


def _to_json_safe(obj):
    """Recursively convert xmlrpc types to JSON-safe Python objects."""
    if isinstance(obj, xmlrpc.client.DateTime):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, dict):
        return {str(k): _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json_safe(i) for i in obj]
    return obj


def _compact(obj) -> str:
    """Serialize to compact JSON."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


# ---------------------------------------------------------------------------
# Response field filtering — strip verbose/unnecessary fields to save tokens.
# Inspired by https://github.com/cvrt-jh/wordpress-mcp (slim.ts).
# ---------------------------------------------------------------------------

_DEFAULT_POST_DROP = "guid,link,ping_status,comment_status,sticky,format,template,class_list,meta,text_more,wp_page_template,wp_password,permaLink,page_status,post_date_gmt,post_modified,post_modified_gmt,post_status,post_type,post_name,post_password,post_excerpt,post_parent,post_mime_type,menu_order,post_thumbnail,post_format,terms,custom_fields"
_DEFAULT_COMMENT_DROP = "author_ip,author_url,link,type,post_title,status,author_email,user_id,post_id,parent"
_DEFAULT_MEDIA_DROP = "link,parent,guid,comment_status,ping_status,sticky,format,template,meta,terms"
_DEFAULT_USER_DROP = "url"


def _parse_csv_set(env_key: str, default: str) -> set[str]:
    raw = os.environ.get(env_key, default)
    return {f.strip() for f in raw.split(",") if f.strip()}


_POST_DROP_FIELDS = _parse_csv_set("WP_DROP_POST_FIELDS", _DEFAULT_POST_DROP)
_COMMENT_DROP_FIELDS = _parse_csv_set("WP_DROP_COMMENT_FIELDS", _DEFAULT_COMMENT_DROP)
_MEDIA_DROP_FIELDS = _parse_csv_set("WP_DROP_MEDIA_FIELDS", _DEFAULT_MEDIA_DROP)
_USER_DROP_FIELDS = _parse_csv_set("WP_DROP_USER_FIELDS", _DEFAULT_USER_DROP)


def _detect_type(obj: dict) -> str:
    """Heuristic to detect the WordPress object type from its fields."""
    if "comment_id" in obj or "comment_parent" in obj:
        return "comment"
    if "attachment_id" in obj or "thumbnail" in obj or "metadata" in obj:
        return "media"
    if "post_id" in obj or "post_title" in obj or "post_type" in obj:
        return "post"
    if "userid" in obj or "user_id" in obj or "roles" in obj or "nickname" in obj:
        return "user"
    # Legacy page responses (wp.getPage)
    if "page_id" in obj or "title" in obj and "dateCreated" in obj:
        return "post"
    return "unknown"


def _drop_fields(obj: dict, drop: set) -> dict:
    return {k: v for k, v in obj.items() if k not in drop}


def _strip_response(obj):
    """Remove unnecessary fields from XML-RPC response data to save tokens.

    Works on dicts and lists of dicts. Non-dict values pass through unchanged.
    """
    if isinstance(obj, dict):
        kind = _detect_type(obj)
        if kind == "post":
            return _drop_fields(obj, _POST_DROP_FIELDS)
        if kind == "comment":
            return _drop_fields(obj, _COMMENT_DROP_FIELDS)
        if kind == "media":
            return _drop_fields(obj, _MEDIA_DROP_FIELDS)
        if kind == "user":
            return _drop_fields(obj, _USER_DROP_FIELDS)
        return obj
    if isinstance(obj, list):
        return [_strip_response(item) for item in obj]
    return obj


# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------

wp = WPClient(
    url=os.environ["WP_URL"],
    username=os.environ["WP_USERNAME"],
    password=os.environ["WP_PASSWORD"],
)

mcp = FastMCP("wordpress-xmlrpc")

# ---------------------------------------------------------------------------
# Enabled tools — configurable via MCP_ENABLED_TOOLS
# ---------------------------------------------------------------------------

_DEFAULT_ENABLED = "getPosts,getPost,getComments,getComment,getCommentCount,getMediaLibrary,getMediaItem"
_ENABLED_TOOLS = _parse_csv_set("MCP_ENABLED_TOOLS", _DEFAULT_ENABLED)


def _tool(func):
    """Register function as MCP tool only if its name is in _ENABLED_TOOLS."""
    if func.__name__ in _ENABLED_TOOLS:
        return mcp.tool()(func)
    return func


# ---------------------------------------------------------------------------
# Tools — posts, comments, media
# ---------------------------------------------------------------------------

@_tool
def getPosts(filters: dict | None = None, fields: list[str] | None = None) -> str:
    """Get posts. filters: {post_type, post_status, number, offset, orderby, order, s, ...}"""
    args = []
    if filters is not None:
        args.append(filters)
    elif fields is not None:
        args.append({})
    if fields is not None:
        args.append(fields)
    return wp.call("wp.getPosts", *args)


@_tool
def getPost(post_id: int, fields: list[str] | None = None) -> str:
    """Get a single post by ID."""
    args = [post_id]
    if fields is not None:
        args.append(fields)
    return wp.call("wp.getPost", *args)


@_tool
def getComments(filters: dict | None = None) -> str:
    """Get comments. filters: {post_id, post_type, status, number, offset}"""
    args = [filters] if filters is not None else []
    return wp.call("wp.getComments", *args)


@_tool
def getComment(comment_id: int) -> str:
    """Get a single comment by ID."""
    return wp.call("wp.getComment", comment_id)


@_tool
def getCommentCount(post_id: int) -> str:
    """Get comment counts for a post."""
    return wp.call("wp.getCommentCount", post_id)


@_tool
def getMediaLibrary(filters: dict | None = None) -> str:
    """Get media items. filters: {number, offset, parent_id, mime_type}"""
    args = [filters] if filters is not None else []
    return wp.call("wp.getMediaLibrary", *args)


@_tool
def getMediaItem(attachment_id: int) -> str:
    """Get a single media item by ID."""
    return wp.call("wp.getMediaItem", attachment_id)


# ---------------------------------------------------------------------------
# Tools — pages, taxonomies, users, options
# ---------------------------------------------------------------------------

@_tool
def getCommentStatusList() -> str:
    """Get available comment statuses."""
    return wp.call("wp.getCommentStatusList")


@_tool
def getPages(num_pages: int = 10) -> str:
    """Get pages. num_pages: max number of pages to return (default 10)."""
    return wp.call("wp.getPages", num_pages)


@_tool
def getPage(page_id: int) -> str:
    """Get a single page by ID."""
    return wp.call_page("wp.getPage", page_id)


@_tool
def getPageList() -> str:
    """Get a simplified list of pages (id, title, parent_id, date)."""
    return wp.call("wp.getPageList")


@_tool
def getPageStatusList() -> str:
    """Get available page statuses."""
    return wp.call("wp.getPageStatusList")


@_tool
def getPageTemplates() -> str:
    """Get available page templates."""
    return wp.call("wp.getPageTemplates")


@_tool
def getPostFormats() -> str:
    """Get available post formats."""
    return wp.call("wp.getPostFormats")


@_tool
def getPostStatusList() -> str:
    """Get available post statuses."""
    return wp.call("wp.getPostStatusList")


@_tool
def getPostType(post_type: str) -> str:
    """Get details of a post type (e.g. 'post', 'page', 'consultation')."""
    return wp.call("wp.getPostType", post_type)


@_tool
def getPostTypes(filters: dict | None = None) -> str:
    """Get all registered post types."""
    args = [filters] if filters is not None else []
    return wp.call("wp.getPostTypes", *args)


@_tool
def getAuthors() -> str:
    """Get all authors."""
    return wp.call("wp.getAuthors")


@_tool
def getUsers(filters: dict | None = None) -> str:
    """Get users. filters: {number, offset, role, who, orderby, order}"""
    args = [filters] if filters is not None else []
    return wp.call("wp.getUsers", *args)


@_tool
def getUser(user_id: int, fields: list[str] | None = None) -> str:
    """Get a single user by ID."""
    args = [user_id]
    if fields is not None:
        args.append(fields)
    return wp.call("wp.getUser", *args)


@_tool
def getProfile() -> str:
    """Get the current user's profile."""
    return wp.call("wp.getProfile")


@_tool
def getCategories() -> str:
    """Get all categories."""
    return wp.call("wp.getCategories")


@_tool
def getTags() -> str:
    """Get all tags."""
    return wp.call("wp.getTags")


@_tool
def getTaxonomies() -> str:
    """Get all registered taxonomies."""
    return wp.call("wp.getTaxonomies")


@_tool
def getTaxonomy(taxonomy: str) -> str:
    """Get details of a taxonomy (e.g. 'category', 'post_tag')."""
    return wp.call("wp.getTaxonomy", taxonomy)


@_tool
def getTerms(taxonomy: str, filters: dict | None = None) -> str:
    """Get terms for a taxonomy. filters: {number, offset, orderby, order, hide_empty, search}"""
    args = [taxonomy]
    if filters is not None:
        args.append(filters)
    return wp.call("wp.getTerms", *args)


@_tool
def getTerm(taxonomy: str, term_id: int) -> str:
    """Get a single term by taxonomy and ID."""
    return wp.call("wp.getTerm", taxonomy, term_id)


@_tool
def getOptions(options: list[str] | None = None) -> str:
    """Get WordPress options. Pass specific option names or None for all."""
    args = [options] if options is not None else []
    return wp.call("wp.getOptions", *args)


@_tool
def getRevisions(post_id: int) -> str:
    """Get revisions for a post."""
    return wp.call("wp.getRevisions", post_id)


# ---------------------------------------------------------------------------
# Tools — write
# ---------------------------------------------------------------------------

@_tool
def newPost(content: dict) -> str:
    """Create a new post. content: {post_type, post_status, post_title, post_content, terms, custom_fields, ...}"""
    return wp.call("wp.newPost", content)


@_tool
def editPost(post_id: int, content: dict) -> str:
    """Edit an existing post. content: {post_title, post_content, post_status, post_type, terms, custom_fields, ...}"""
    return wp.call("wp.editPost", post_id, content)


@_tool
def newComment(post_id: int, comment: dict) -> str:
    """Create a comment. comment: {content, author, author_url, author_email}"""
    return wp.call("wp.newComment", post_id, comment)


@_tool
def editComment(comment_id: int, comment: dict) -> str:
    """Edit a comment. comment: {status, date_created_gmt, content, author, author_url, author_email}"""
    return wp.call("wp.editComment", comment_id, comment)


@_tool
def newPage(content: dict) -> str:
    """Create a new page (legacy). content: {title, description (body HTML), wp_page_template, wp_page_order, ...}"""
    return wp.call("wp.newPage", content)


@_tool
def editPage(page_id: int, content: dict, publish: int = 0) -> str:
    """Edit a page. content: page fields struct. publish: 1 to publish, 0 for draft (default 0)."""
    return wp.call_page("wp.editPage", page_id, content, publish)


@_tool
def editProfile(content: dict) -> str:
    """Edit current user profile. content: {first_name, last_name, url, display_name, nickname, nicename (URL slug), bio}"""
    return wp.call("wp.editProfile", content)


@_tool
def newCategory(category: dict) -> str:
    """Create a category. category: {name, slug, parent_id, description}"""
    return wp.call("wp.newCategory", category)


@_tool
def newTerm(content: dict) -> str:
    """Create a term. content: {taxonomy, name, slug, parent, description}. taxonomy is required."""
    return wp.call("wp.newTerm", content)


@_tool
def editTerm(term_id: int, term: dict) -> str:
    """Edit a term. term: {taxonomy (required), name, slug, parent, description}"""
    return wp.call("wp.editTerm", term_id, term)


@_tool
def setOptions(options: dict) -> str:
    """Set WordPress options. options: {option_name: option_value, ...}"""
    return wp.call("wp.setOptions", options)


@_tool
def uploadFile(data: dict) -> str:
    """Upload a file. data: {name (required), type (required, e.g. 'image/png'), bits (required, base64-encoded)}"""
    return wp.call("wp.uploadFile", data)


@_tool
def suggestCategories(category: str, max_results: int = 10) -> str:
    """Suggest categories matching a string."""
    return wp.call("wp.suggestCategories", category, max_results)


@_tool
def restoreRevision(revision_id: int) -> str:
    """Restore a post revision."""
    return wp.call("wp.restoreRevision", revision_id)


# ---------------------------------------------------------------------------
# Tools — delete
# ---------------------------------------------------------------------------

@_tool
def deletePost(post_id: int) -> str:
    """Delete a post."""
    return wp.call("wp.deletePost", post_id)


@_tool
def deleteComment(comment_id: int) -> str:
    """Delete a comment."""
    return wp.call("wp.deleteComment", comment_id)


@_tool
def deletePage(page_id: int) -> str:
    """Delete a page."""
    return wp.call("wp.deletePage", page_id)


@_tool
def deleteCategory(category_id: int) -> str:
    """Delete a category."""
    return wp.call("wp.deleteCategory", category_id)


@_tool
def deleteTerm(taxonomy: str, term_id: int) -> str:
    """Delete a term by taxonomy name and term ID."""
    return wp.call("wp.deleteTerm", taxonomy, term_id)


@_tool
def deleteFile(attachment_id: int) -> str:
    """Delete a media file (attachment) by ID."""
    return wp.call("wp.deleteFile", attachment_id)


def main():
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    kwargs = {}
    if transport in ("sse", "streamable-http"):
        kwargs["host"] = os.environ.get("MCP_HOST", "0.0.0.0")
        kwargs["port"] = int(os.environ.get("MCP_PORT", "8000"))
    mcp.run(transport=transport, **kwargs)


if __name__ == "__main__":
    main()
