"""
Confluence Cloud MCP tools.

All 30 @mcp.tool() decorated functions that expose the Confluence REST API v2
to MCP clients. The tools are registered on the FastMCP instance defined in
server.py, which imports this module as a side effect.
"""

from __future__ import annotations

from typing import Any, Optional

from mcp.types import ToolAnnotations

from confluence_mcp.client import (
    _VALID_BODY_REPRESENTATIONS,
    _VALID_SPACE_TYPES,
    _VALID_SPACE_STATUSES,
    check_enum,
    clean,
    require_str,
    request,
    v1,
    v2,
)
from confluence_mcp.server import mcp

# ---------------------------------------------------------------------------
# Tool annotation constants
# ---------------------------------------------------------------------------

_READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, openWorldHint=True
)
_CREATE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
)
_UPDATE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True
)
_DESTROY = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True
)


# ===========================================================================
# Pages — CRUD
# ===========================================================================


@mcp.tool(title="List Pages", annotations=_READ_ONLY)
def list_pages(
    space_id: Optional[str] = None,
    title: Optional[str] = None,
    status: Optional[str] = None,
    ancestor_id: Optional[str] = None,
    sort: Optional[str] = None,
    limit: Optional[int] = None,
    cursor: Optional[str] = None,
) -> Any:
    """List pages, optionally filtered by space, title, status, or parent.

    Args:
        space_id: Filter by space ID.
        title: Exact title match.
        status: Page status — current, archived, trashed, deleted.
        ancestor_id: Filter by parent page ID.
        sort: Sort field, e.g. 'title', '-title', 'created-date', '-modified-date'.
        limit: Max results (1–250).
        cursor: Pagination cursor from a previous response.
    """
    check_enum(status, "status", {"current", "archived", "trashed", "deleted"})
    return request(
        "GET",
        v2("/pages"),
        params=clean(
            {
                "space-id": space_id,
                "title": title,
                "status": status,
                "ancestor-id": ancestor_id,
                "sort": sort,
                "limit": limit,
                "cursor": cursor,
            }
        ),
    )


@mcp.tool(title="Get Page", annotations=_READ_ONLY)
def get_page(
    page_id: str,
    body_format: Optional[str] = None,
    get_draft: Optional[bool] = None,
    version: Optional[int] = None,
) -> Any:
    """Get a page by ID.

    Args:
        page_id: Page ID.
        body_format: Body representation — storage (XHTML), view, atlas_doc_format.
        get_draft: If True, return the current draft instead of published version.
        version: Return a specific historical version number.
    """
    require_str(page_id, "page_id")
    check_enum(body_format, "body_format", {"storage", "view", "atlas_doc_format"})
    return request(
        "GET",
        v2(f"/pages/{page_id}"),
        params=clean(
            {"body-format": body_format, "get-draft": get_draft, "version": version}
        ),
    )


@mcp.tool(title="Create Page", annotations=_CREATE)
def create_page(
    space_id: str,
    title: str,
    body_value: str,
    body_representation: str = "storage",
    parent_id: Optional[str] = None,
    status: str = "current",
) -> Any:
    """Create a new page in a space.

    Args:
        space_id: Target space ID.
        title: Page title.
        body_value: Page body content.
        body_representation: Format of body_value — storage (default, XHTML), wiki, atlas_doc_format.
        parent_id: Parent page ID (omit to create at space root).
        status: 'current' (published, default) or 'draft'.
    """
    require_str(space_id, "space_id")
    require_str(title, "title")
    check_enum(body_representation, "body_representation", _VALID_BODY_REPRESENTATIONS)
    check_enum(status, "status", {"current", "draft"})
    payload: dict[str, Any] = {
        "spaceId": space_id,
        "title": title,
        "body": {"representation": body_representation, "value": body_value},
        "status": status,
    }
    if parent_id:
        payload["parentId"] = parent_id
    return request("POST", v2("/pages"), json=payload)


@mcp.tool(title="Update Page", annotations=_UPDATE)
def update_page(
    page_id: str,
    title: str,
    body_value: str,
    version_number: int,
    body_representation: str = "storage",
    status: str = "current",
    parent_id: Optional[str] = None,
    owner_id: Optional[str] = None,
    version_message: Optional[str] = None,
) -> Any:
    """Update an existing page (content, title, parent, or owner).

    To move a page to a different parent within the same space, pass the new
    parent_id. Cross-space moves are not supported by the v2 API.
    To transfer ownership, pass the new owner's account ID as owner_id.

    Args:
        page_id: ID of the page to update.
        title: New (or unchanged) title.
        body_value: New (or unchanged) body content.
        version_number: The next version number to store — must be current version + 1.
        body_representation: Format of body_value — storage (default), wiki, atlas_doc_format.
        status: 'current' (published) or 'draft'.
        parent_id: New parent page ID to move/reparent the page (same space only).
        owner_id: Atlassian account ID of the new page owner.
        version_message: Optional commit message stored in the version history.
    """
    require_str(page_id, "page_id")
    require_str(title, "title")
    check_enum(body_representation, "body_representation", _VALID_BODY_REPRESENTATIONS)
    check_enum(status, "status", {"current", "draft"})
    if version_number < 1:
        raise ValueError("'version_number' must be a positive integer.")
    version: dict[str, Any] = {"number": version_number}
    if version_message:
        version["message"] = version_message

    payload: dict[str, Any] = {
        "id": page_id,
        "title": title,
        "body": {"representation": body_representation, "value": body_value},
        "version": version,
        "status": status,
    }
    if parent_id:
        payload["parentId"] = parent_id
    if owner_id:
        payload["ownerId"] = owner_id
    return request("PUT", v2(f"/pages/{page_id}"), json=payload)


@mcp.tool(title="Delete Page", annotations=_DESTROY)
def delete_page(page_id: str, purge: bool = False) -> Any:
    """Delete a page (moves to trash by default).

    To permanently delete, first call delete_page to trash the page, then call
    delete_page again with purge=True.

    Args:
        page_id: ID of the page to delete.
        purge: If True, permanently delete a trashed page. The page must already
               be in the trash; calling purge=True on a current page returns 400.
    """
    require_str(page_id, "page_id")
    return request(
        "DELETE",
        v2(f"/pages/{page_id}"),
        params={"purge": "true"} if purge else None,
    )


@mcp.tool(title="Restore Page", annotations=_UPDATE)
def restore_page(
    page_id: str,
    title: str,
    body_value: str,
    version_number: int,
    body_representation: str = "storage",
    parent_id: Optional[str] = None,
) -> Any:
    """Restore a trashed page by setting its status back to 'current'.

    Args:
        page_id: ID of the trashed page.
        title: Page title (unchanged or new).
        body_value: Page body content (unchanged or new).
        version_number: The next version number to store — must be current version + 1.
        body_representation: Format of body_value — storage (default), wiki, atlas_doc_format.
        parent_id: Parent page ID (required if the original parent was also deleted).
    """
    require_str(page_id, "page_id")
    require_str(title, "title")
    check_enum(body_representation, "body_representation", _VALID_BODY_REPRESENTATIONS)
    if version_number < 1:
        raise ValueError("'version_number' must be a positive integer.")
    payload: dict[str, Any] = {
        "id": page_id,
        "title": title,
        "body": {"representation": body_representation, "value": body_value},
        "version": {"number": version_number},
        "status": "current",
    }
    if parent_id:
        payload["parentId"] = parent_id
    return request("PUT", v2(f"/pages/{page_id}"), json=payload)


@mcp.tool(title="Get Page Operations", annotations=_READ_ONLY)
def get_page_operations(page_id: str) -> Any:
    """Get the permitted operations (read, update, delete, …) for a page.

    Args:
        page_id: Page ID.
    """
    require_str(page_id, "page_id")
    return request("GET", v2(f"/pages/{page_id}/operations"))


# ===========================================================================
# Pages — navigation
# ===========================================================================


@mcp.tool(title="Get Page Children", annotations=_READ_ONLY)
def get_page_children(
    page_id: str,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
    sort: Optional[str] = None,
) -> Any:
    """Get all child pages of a page (recursive, paginated).

    Args:
        page_id: Parent page ID.
        cursor: Pagination cursor.
        limit: Max results.
        sort: Sort field.
    """
    require_str(page_id, "page_id")
    return request(
        "GET",
        v2(f"/pages/{page_id}/children"),
        params=clean({"cursor": cursor, "limit": limit, "sort": sort}),
    )


@mcp.tool(title="Get Page Direct Children", annotations=_READ_ONLY)
def get_page_direct_children(
    page_id: str,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Any:
    """Get the immediate (one-level-deep) children of a page.

    Args:
        page_id: Parent page ID.
        cursor: Pagination cursor.
        limit: Max results.
    """
    require_str(page_id, "page_id")
    return request(
        "GET",
        v2(f"/pages/{page_id}/direct-children"),
        params=clean({"cursor": cursor, "limit": limit}),
    )


@mcp.tool(title="Get Page Ancestors", annotations=_READ_ONLY)
def get_page_ancestors(page_id: str) -> Any:
    """Get all ancestor pages (breadcrumb trail) for a page.

    Args:
        page_id: Page ID.
    """
    require_str(page_id, "page_id")
    return request("GET", v2(f"/pages/{page_id}/ancestors"))


@mcp.tool(title="Get Page Descendants", annotations=_READ_ONLY)
def get_page_descendants(
    page_id: str,
    limit: Optional[int] = None,
    cursor: Optional[str] = None,
) -> Any:
    """Get all descendants of a page.

    Args:
        page_id: Page ID.
        limit: Max results.
        cursor: Pagination cursor.
    """
    require_str(page_id, "page_id")
    return request(
        "GET",
        v2(f"/pages/{page_id}/descendants"),
        params=clean({"limit": limit, "cursor": cursor}),
    )


# ===========================================================================
# Spaces
# ===========================================================================


@mcp.tool(title="List Spaces", annotations=_READ_ONLY)
def list_spaces(
    ids: Optional[str] = None,
    keys: Optional[str] = None,
    type: Optional[str] = None,
    status: Optional[str] = None,
    labels: Optional[str] = None,
    sort: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Any:
    """List Confluence spaces.

    Args:
        ids: Comma-separated space IDs to filter by.
        keys: Comma-separated space keys to filter by.
        type: Space type — 'global' or 'personal'.
        status: Space status — 'current' or 'archived'.
        labels: Comma-separated labels to filter by.
        sort: Sort field, e.g. 'name', '-name', 'key'.
        cursor: Pagination cursor.
        limit: Max results.
    """
    check_enum(type, "type", _VALID_SPACE_TYPES)
    check_enum(status, "status", _VALID_SPACE_STATUSES)
    return request(
        "GET",
        v2("/spaces"),
        params=clean(
            {
                "ids": ids,
                "keys": keys,
                "type": type,
                "status": status,
                "labels": labels,
                "sort": sort,
                "cursor": cursor,
                "limit": limit,
            }
        ),
    )


@mcp.tool(title="Get Space", annotations=_READ_ONLY)
def get_space(space_id: str) -> Any:
    """Get a space by its ID.

    Args:
        space_id: Space ID.
    """
    require_str(space_id, "space_id")
    return request("GET", v2(f"/spaces/{space_id}"))


@mcp.tool(title="List Pages in Space", annotations=_READ_ONLY)
def list_pages_in_space(
    space_id: str,
    depth: Optional[str] = None,
    sort: Optional[str] = None,
    status: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Any:
    """List all pages in a space.

    Args:
        space_id: Space ID.
        depth: 'all' (default) or 'root' (top-level pages only).
        sort: Sort field.
        status: Page status filter.
        cursor: Pagination cursor.
        limit: Max results.
    """
    require_str(space_id, "space_id")
    check_enum(depth, "depth", {"all", "root"})
    check_enum(status, "status", {"current", "archived", "trashed", "deleted"})
    return request(
        "GET",
        v2(f"/spaces/{space_id}/pages"),
        params=clean(
            {
                "depth": depth,
                "sort": sort,
                "status": status,
                "cursor": cursor,
                "limit": limit,
            }
        ),
    )


@mcp.tool(title="List Blog Posts in Space", annotations=_READ_ONLY)
def list_blogposts_in_space(
    space_id: str,
    sort: Optional[str] = None,
    status: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Any:
    """List blog posts in a space.

    Args:
        space_id: Space ID.
        sort: Sort field.
        status: Blog post status filter.
        cursor: Pagination cursor.
        limit: Max results.
    """
    require_str(space_id, "space_id")
    return request(
        "GET",
        v2(f"/spaces/{space_id}/blogposts"),
        params=clean(
            {"sort": sort, "status": status, "cursor": cursor, "limit": limit}
        ),
    )


@mcp.tool(title="Get Space Permissions", annotations=_READ_ONLY)
def get_space_permissions(
    space_id: str,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Any:
    """Get permission assignments for a space.

    Args:
        space_id: Space ID.
        cursor: Pagination cursor.
        limit: Max results.
    """
    require_str(space_id, "space_id")
    return request(
        "GET",
        v2(f"/spaces/{space_id}/permissions"),
        params=clean({"cursor": cursor, "limit": limit}),
    )


# ===========================================================================
# Labels (read-only — write operations are v1 API only)
# ===========================================================================


@mcp.tool(title="List Page Labels", annotations=_READ_ONLY)
def list_page_labels(
    page_id: str,
    prefix: Optional[str] = None,
    sort: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Any:
    """List labels attached to a page.

    Args:
        page_id: Page ID.
        prefix: Filter by label prefix (e.g. 'global', 'team').
        sort: Sort field.
        cursor: Pagination cursor.
        limit: Max results.
    """
    require_str(page_id, "page_id")
    return request(
        "GET",
        v2(f"/pages/{page_id}/labels"),
        params=clean(
            {"prefix": prefix, "sort": sort, "cursor": cursor, "limit": limit}
        ),
    )


@mcp.tool(title="List Space Labels", annotations=_READ_ONLY)
def list_space_labels(
    space_id: str,
    prefix: Optional[str] = None,
    sort: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Any:
    """List labels used across a space.

    Args:
        space_id: Space ID.
        prefix: Filter by label prefix.
        sort: Sort field.
        cursor: Pagination cursor.
        limit: Max results.
    """
    require_str(space_id, "space_id")
    return request(
        "GET",
        v2(f"/spaces/{space_id}/labels"),
        params=clean(
            {"prefix": prefix, "sort": sort, "cursor": cursor, "limit": limit}
        ),
    )


@mcp.tool(title="List Pages with Label", annotations=_READ_ONLY)
def list_pages_with_label(
    label_id: str,
    space_id: Optional[str] = None,
    body_format: Optional[str] = None,
    sort: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Any:
    """List all pages that carry a specific label.

    Args:
        label_id: Label ID.
        space_id: Narrow results to a specific space.
        body_format: Body representation in the returned pages.
        sort: Sort field.
        cursor: Pagination cursor.
        limit: Max results.
    """
    require_str(label_id, "label_id")
    check_enum(body_format, "body_format", {"storage", "view", "atlas_doc_format"})
    return request(
        "GET",
        v2(f"/labels/{label_id}/pages"),
        params=clean(
            {
                "space-id": space_id,
                "body-format": body_format,
                "sort": sort,
                "cursor": cursor,
                "limit": limit,
            }
        ),
    )


# ===========================================================================
# Versions
# ===========================================================================


@mcp.tool(title="List Page Versions", annotations=_READ_ONLY)
def list_page_versions(
    page_id: str,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
    sort: Optional[str] = None,
) -> Any:
    """List the version history of a page.

    Args:
        page_id: Page ID.
        cursor: Pagination cursor.
        limit: Max results.
        sort: Sort field — 'created-date' (oldest first) or '-created-date' (newest first).
    """
    require_str(page_id, "page_id")
    return request(
        "GET",
        v2(f"/pages/{page_id}/versions"),
        params=clean({"cursor": cursor, "limit": limit, "sort": sort}),
    )


@mcp.tool(title="Get Page Version", annotations=_READ_ONLY)
def get_page_version(page_id: str, version_number: int) -> Any:
    """Get details for a specific version of a page.

    Args:
        page_id: Page ID.
        version_number: Version number to retrieve.
    """
    require_str(page_id, "page_id")
    if version_number < 1:
        raise ValueError("'version_number' must be a positive integer.")
    return request("GET", v2(f"/pages/{page_id}/versions/{version_number}"))


# ===========================================================================
# Footer Comments
# ===========================================================================


@mcp.tool(title="List Page Footer Comments", annotations=_READ_ONLY)
def list_page_footer_comments(
    page_id: str,
    body_format: Optional[str] = None,
    sort: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Any:
    """List footer (page-level) comments on a page.

    Args:
        page_id: Page ID.
        body_format: Body representation — storage, view, atlas_doc_format.
        sort: Sort field.
        cursor: Pagination cursor.
        limit: Max results.
    """
    require_str(page_id, "page_id")
    check_enum(body_format, "body_format", {"storage", "view", "atlas_doc_format"})
    return request(
        "GET",
        v2(f"/pages/{page_id}/footer-comments"),
        params=clean(
            {"body-format": body_format, "sort": sort, "cursor": cursor, "limit": limit}
        ),
    )


@mcp.tool(title="Get Footer Comment", annotations=_READ_ONLY)
def get_footer_comment(
    comment_id: str,
    body_format: Optional[str] = None,
    version: Optional[int] = None,
) -> Any:
    """Get a footer comment by ID.

    Args:
        comment_id: Comment ID.
        body_format: Body representation.
        version: Specific version number.
    """
    require_str(comment_id, "comment_id")
    check_enum(body_format, "body_format", {"storage", "view", "atlas_doc_format"})
    return request(
        "GET",
        v2(f"/footer-comments/{comment_id}"),
        params=clean({"body-format": body_format, "version": version}),
    )


@mcp.tool(title="Create Footer Comment", annotations=_CREATE)
def create_footer_comment(
    body_value: str,
    page_id: Optional[str] = None,
    blogpost_id: Optional[str] = None,
    parent_comment_id: Optional[str] = None,
    body_representation: str = "storage",
) -> Any:
    """Create a footer comment on a page or blog post, or reply to an existing comment.

    Provide exactly one of page_id, blogpost_id, or parent_comment_id.

    Args:
        body_value: Comment body content.
        page_id: Page to comment on.
        blogpost_id: Blog post to comment on.
        parent_comment_id: Parent comment ID (to create a reply).
        body_representation: Format of body_value — storage (default), wiki, atlas_doc_format.
    """
    targets = [x for x in (page_id, blogpost_id, parent_comment_id) if x]
    if len(targets) != 1:
        raise ValueError(
            "Provide exactly one of 'page_id', 'blogpost_id', or 'parent_comment_id'."
        )
    check_enum(body_representation, "body_representation", _VALID_BODY_REPRESENTATIONS)
    payload: dict[str, Any] = {
        "body": {"representation": body_representation, "value": body_value}
    }
    if page_id:
        payload["pageId"] = page_id
    if blogpost_id:
        payload["blogPostId"] = blogpost_id
    if parent_comment_id:
        payload["parentCommentId"] = parent_comment_id
    return request("POST", v2("/footer-comments"), json=payload)


@mcp.tool(title="Update Footer Comment", annotations=_UPDATE)
def update_footer_comment(
    comment_id: str,
    body_value: str,
    version_number: int,
    body_representation: str = "storage",
) -> Any:
    """Update an existing footer comment.

    Args:
        comment_id: Comment ID.
        body_value: New comment content.
        version_number: The next version number to store — must be current version + 1.
        body_representation: Format of body_value — storage (default), wiki, atlas_doc_format.
    """
    require_str(comment_id, "comment_id")
    check_enum(body_representation, "body_representation", _VALID_BODY_REPRESENTATIONS)
    if version_number < 1:
        raise ValueError("'version_number' must be a positive integer.")
    return request(
        "PUT",
        v2(f"/footer-comments/{comment_id}"),
        json={
            "version": {"number": version_number},
            "body": {"representation": body_representation, "value": body_value},
        },
    )


@mcp.tool(title="Delete Footer Comment", annotations=_DESTROY)
def delete_footer_comment(comment_id: str) -> Any:
    """Delete a footer comment.

    Args:
        comment_id: Comment ID.
    """
    require_str(comment_id, "comment_id")
    return request("DELETE", v2(f"/footer-comments/{comment_id}"))


@mcp.tool(title="List Footer Comment Replies", annotations=_READ_ONLY)
def list_footer_comment_replies(
    comment_id: str,
    body_format: Optional[str] = None,
    sort: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Any:
    """List replies (child comments) of a footer comment.

    Args:
        comment_id: Parent comment ID.
        body_format: Body representation.
        sort: Sort field.
        cursor: Pagination cursor.
        limit: Max results.
    """
    require_str(comment_id, "comment_id")
    check_enum(body_format, "body_format", {"storage", "view", "atlas_doc_format"})
    return request(
        "GET",
        v2(f"/footer-comments/{comment_id}/children"),
        params=clean(
            {"body-format": body_format, "sort": sort, "cursor": cursor, "limit": limit}
        ),
    )


# ===========================================================================
# Inline Comments
# ===========================================================================


@mcp.tool(title="List Page Inline Comments", annotations=_READ_ONLY)
def list_page_inline_comments(
    page_id: str,
    body_format: Optional[str] = None,
    sort: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Any:
    """List inline comments on a page.

    Args:
        page_id: Page ID.
        body_format: Body representation.
        sort: Sort field.
        cursor: Pagination cursor.
        limit: Max results.
    """
    require_str(page_id, "page_id")
    check_enum(body_format, "body_format", {"storage", "view", "atlas_doc_format"})
    return request(
        "GET",
        v2(f"/pages/{page_id}/inline-comments"),
        params=clean(
            {"body-format": body_format, "sort": sort, "cursor": cursor, "limit": limit}
        ),
    )


@mcp.tool(title="Get Inline Comment", annotations=_READ_ONLY)
def get_inline_comment(
    comment_id: str,
    body_format: Optional[str] = None,
    version: Optional[int] = None,
) -> Any:
    """Get an inline comment by ID.

    Args:
        comment_id: Comment ID.
        body_format: Body representation.
        version: Specific version number.
    """
    require_str(comment_id, "comment_id")
    check_enum(body_format, "body_format", {"storage", "view", "atlas_doc_format"})
    return request(
        "GET",
        v2(f"/inline-comments/{comment_id}"),
        params=clean({"body-format": body_format, "version": version}),
    )


@mcp.tool(title="Update Inline Comment", annotations=_UPDATE)
def update_inline_comment(
    comment_id: str,
    body_value: str,
    version_number: int,
    body_representation: str = "storage",
    resolved: Optional[bool] = None,
) -> Any:
    """Update an inline comment (content or resolved state).

    Args:
        comment_id: Comment ID.
        body_value: New comment content.
        version_number: The next version number to store — must be current version + 1.
        body_representation: Format of body_value — storage (default), wiki, atlas_doc_format.
        resolved: Set to True to mark the comment thread as resolved, False to reopen.
    """
    require_str(comment_id, "comment_id")
    check_enum(body_representation, "body_representation", _VALID_BODY_REPRESENTATIONS)
    if version_number < 1:
        raise ValueError("'version_number' must be a positive integer.")
    payload: dict[str, Any] = {
        "version": {"number": version_number},
        "body": {"representation": body_representation, "value": body_value},
    }
    if resolved is not None:
        payload["resolved"] = resolved
    return request("PUT", v2(f"/inline-comments/{comment_id}"), json=payload)


@mcp.tool(title="Delete Inline Comment", annotations=_DESTROY)
def delete_inline_comment(comment_id: str) -> Any:
    """Delete an inline comment.

    Args:
        comment_id: Comment ID.
    """
    require_str(comment_id, "comment_id")
    return request("DELETE", v2(f"/inline-comments/{comment_id}"))


# ===========================================================================
# Attachments (read + delete only — upload requires multipart form)
# ===========================================================================


@mcp.tool(title="List Page Attachments", annotations=_READ_ONLY)
def list_page_attachments(
    page_id: str,
    sort: Optional[str] = None,
    cursor: Optional[str] = None,
    status: Optional[str] = None,
    mediatype: Optional[str] = None,
    filename: Optional[str] = None,
    limit: Optional[int] = None,
) -> Any:
    """List attachments on a page.

    Args:
        page_id: Page ID.
        sort: Sort field.
        cursor: Pagination cursor.
        status: Attachment status filter.
        mediatype: MIME type filter, e.g. 'image/png'.
        filename: Filename filter.
        limit: Max results.
    """
    require_str(page_id, "page_id")
    return request(
        "GET",
        v2(f"/pages/{page_id}/attachments"),
        params=clean(
            {
                "sort": sort,
                "cursor": cursor,
                "status": status,
                "mediatype": mediatype,
                "filename": filename,
                "limit": limit,
            }
        ),
    )


@mcp.tool(title="Get Attachment", annotations=_READ_ONLY)
def get_attachment(
    attachment_id: str,
    version: Optional[int] = None,
) -> Any:
    """Get an attachment by ID.

    Args:
        attachment_id: Attachment ID.
        version: Specific version number.
    """
    require_str(attachment_id, "attachment_id")
    return request(
        "GET",
        v2(f"/attachments/{attachment_id}"),
        params=clean({"version": version}),
    )


@mcp.tool(title="Delete Attachment", annotations=_DESTROY)
def delete_attachment(attachment_id: str) -> Any:
    """Delete an attachment.

    Args:
        attachment_id: Attachment ID.
    """
    require_str(attachment_id, "attachment_id")
    return request("DELETE", v2(f"/attachments/{attachment_id}"))


# ===========================================================================
# Content Properties (page-level key/value metadata)
# ===========================================================================


@mcp.tool(title="List Page Properties", annotations=_READ_ONLY)
def list_page_properties(
    page_id: str,
    key: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Any:
    """List content properties on a page.

    Args:
        page_id: Page ID.
        key: Filter by property key.
        cursor: Pagination cursor.
        limit: Max results.
    """
    require_str(page_id, "page_id")
    return request(
        "GET",
        v2(f"/pages/{page_id}/properties"),
        params=clean({"key": key, "cursor": cursor, "limit": limit}),
    )


@mcp.tool(title="Get Page Property", annotations=_READ_ONLY)
def get_page_property(page_id: str, property_id: str) -> Any:
    """Get a specific content property on a page.

    Args:
        page_id: Page ID.
        property_id: Property ID.
    """
    require_str(page_id, "page_id")
    require_str(property_id, "property_id")
    return request("GET", v2(f"/pages/{page_id}/properties/{property_id}"))


@mcp.tool(title="Create Page Property", annotations=_CREATE)
def create_page_property(page_id: str, key: str, value: Any) -> Any:
    """Create a content property on a page.

    Args:
        page_id: Page ID.
        key: Property key (must be unique on the page).
        value: Property value — any JSON-serializable value.
    """
    require_str(page_id, "page_id")
    require_str(key, "key")
    return request(
        "POST", v2(f"/pages/{page_id}/properties"), json={"key": key, "value": value}
    )


@mcp.tool(title="Update Page Property", annotations=_UPDATE)
def update_page_property(
    page_id: str,
    property_id: str,
    key: str,
    value: Any,
    version_number: int,
) -> Any:
    """Update a content property on a page.

    Args:
        page_id: Page ID.
        property_id: Property ID.
        key: Property key.
        value: New property value.
        version_number: The next version number to store — must be current version + 1.
    """
    require_str(page_id, "page_id")
    require_str(property_id, "property_id")
    require_str(key, "key")
    if version_number < 1:
        raise ValueError("'version_number' must be a positive integer.")
    return request(
        "PUT",
        v2(f"/pages/{page_id}/properties/{property_id}"),
        json={"key": key, "value": value, "version": {"number": version_number}},
    )


@mcp.tool(title="Delete Page Property", annotations=_DESTROY)
def delete_page_property(page_id: str, property_id: str) -> Any:
    """Delete a content property from a page.

    Args:
        page_id: Page ID.
        property_id: Property ID.
    """
    require_str(page_id, "page_id")
    require_str(property_id, "property_id")
    return request("DELETE", v2(f"/pages/{page_id}/properties/{property_id}"))


# ===========================================================================
# Tasks
# ===========================================================================


@mcp.tool(title="List Tasks", annotations=_READ_ONLY)
def list_tasks(
    status: Optional[str] = None,
    space_id: Optional[str] = None,
    page_id: Optional[str] = None,
    assigned_to: Optional[str] = None,
    created_by: Optional[str] = None,
    due_at_from: Optional[str] = None,
    due_at_to: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Any:
    """List tasks in Confluence.

    Args:
        status: Task status — 'open' or 'complete'.
        space_id: Filter by space ID.
        page_id: Filter by page ID.
        assigned_to: Filter by assignee account ID.
        created_by: Filter by creator account ID.
        due_at_from: ISO 8601 — tasks due on or after this date.
        due_at_to: ISO 8601 — tasks due on or before this date.
        cursor: Pagination cursor.
        limit: Max results.
    """
    check_enum(status, "status", {"open", "complete"})
    return request(
        "GET",
        v2("/tasks"),
        params=clean(
            {
                "status": status,
                "space-id": space_id,
                "page-id": page_id,
                "assigned-to": assigned_to,
                "created-by": created_by,
                "due-at-from": due_at_from,
                "due-at-to": due_at_to,
                "cursor": cursor,
                "limit": limit,
            }
        ),
    )


@mcp.tool(title="Get Task", annotations=_READ_ONLY)
def get_task(task_id: str, body_format: Optional[str] = None) -> Any:
    """Get a task by ID.

    Args:
        task_id: Task ID.
        body_format: Body representation for the task content.
    """
    require_str(task_id, "task_id")
    check_enum(body_format, "body_format", {"storage", "view", "atlas_doc_format"})
    return request(
        "GET",
        v2(f"/tasks/{task_id}"),
        params=clean({"body-format": body_format}),
    )


@mcp.tool(title="Update Task", annotations=_UPDATE)
def update_task(
    task_id: str,
    status: str,
    assigned_to: Optional[str] = None,
    due_at: Optional[str] = None,
) -> Any:
    """Update a task's status, assignee, or due date.

    Args:
        task_id: Task ID.
        status: New status — 'open' or 'complete'.
        assigned_to: Account ID of the new assignee.
        due_at: ISO 8601 due date.
    """
    require_str(task_id, "task_id")
    check_enum(status, "status", {"open", "complete", "incomplete"})
    payload: dict[str, Any] = {"status": status}
    if assigned_to:
        payload["assignedTo"] = assigned_to
    if due_at:
        payload["dueAt"] = due_at
    return request("PUT", v2(f"/tasks/{task_id}"), json=payload)


# ===========================================================================
# Utility
# ===========================================================================


@mcp.tool(title="Convert IDs to Types", annotations=_READ_ONLY)
def convert_ids_to_types(content_ids: list[str]) -> Any:
    """Convert a list of content IDs to their content types (page, blogpost, etc.).

    Useful when you have an ID but don't know whether it refers to a page,
    blog post, attachment, or other content type.

    Args:
        content_ids: List of content IDs to look up.
    """
    if not content_ids:
        raise ValueError("'content_ids' must be a non-empty list.")
    return request(
        "POST",
        v2("/content/convert-ids-to-types"),
        json={"contentIds": content_ids},
    )


# ===========================================================================
# Spaces — extended (create + properties CRUD + operations + content labels)
# ===========================================================================


@mcp.tool(title="Create Space", annotations=_CREATE)
def create_space(
    key: str,
    name: str,
    description: Optional[str] = None,
) -> Any:
    """Create a new Confluence space.

    Args:
        key: Unique space key (e.g. 'ENG'). Must be uppercase letters/numbers.
        name: Human-readable space name.
        description: Optional plain-text description of the space.
    """
    require_str(key, "key")
    require_str(name, "name")
    payload: dict[str, Any] = {"key": key, "name": name}
    if description:
        payload["description"] = {
            "representation": "plain",
            "value": description,
        }
    return request("POST", v2("/spaces"), json=payload)


@mcp.tool(title="Get Space Operations", annotations=_READ_ONLY)
def get_space_operations(space_id: str) -> Any:
    """Get the operations (permissions) available to the current user in a space.

    Args:
        space_id: The ID of the space.
    """
    require_str(space_id, "space_id")
    return request("GET", v2(f"/spaces/{space_id}/operations"))


@mcp.tool(title="Get Space Content Labels", annotations=_READ_ONLY)
def get_space_content_labels(
    space_id: str,
    prefix: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Any:
    """List all labels used on content within a space.

    Args:
        space_id: The ID of the space.
        prefix: Filter by label prefix (e.g. 'global', 'my', 'team').
        cursor: Pagination cursor from a previous response.
        limit: Max results to return (default 25, max 250).
    """
    require_str(space_id, "space_id")
    return request(
        "GET",
        v2(f"/spaces/{space_id}/content/labels"),
        params=clean({"prefix": prefix, "cursor": cursor, "limit": limit}),
    )


@mcp.tool(title="List Space Properties", annotations=_READ_ONLY)
def list_space_properties(
    space_id: str,
    key: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Any:
    """List content properties of a space.

    Args:
        space_id: The ID of the space.
        key: Filter by property key.
        cursor: Pagination cursor from a previous response.
        limit: Max results to return.
    """
    require_str(space_id, "space_id")
    return request(
        "GET",
        v2(f"/spaces/{space_id}/properties"),
        params=clean({"key": key, "cursor": cursor, "limit": limit}),
    )


@mcp.tool(title="Get Space Property", annotations=_READ_ONLY)
def get_space_property(space_id: str, property_id: str) -> Any:
    """Get a single content property of a space by its ID.

    Args:
        space_id: The ID of the space.
        property_id: The ID of the property.
    """
    require_str(space_id, "space_id")
    require_str(property_id, "property_id")
    return request("GET", v2(f"/spaces/{space_id}/properties/{property_id}"))


@mcp.tool(title="Create Space Property", annotations=_CREATE)
def create_space_property(space_id: str, key: str, value: Any) -> Any:
    """Create a new content property on a space.

    Args:
        space_id: The ID of the space.
        key: Property key (must be unique within the space).
        value: Property value (string, number, dict, or list).
    """
    require_str(space_id, "space_id")
    require_str(key, "key")
    return request(
        "POST",
        v2(f"/spaces/{space_id}/properties"),
        json={"key": key, "value": value},
    )


@mcp.tool(title="Update Space Property", annotations=_UPDATE)
def update_space_property(
    space_id: str,
    property_id: str,
    key: str,
    value: Any,
    version_number: int,
) -> Any:
    """Update an existing content property on a space.

    Args:
        space_id: The ID of the space.
        property_id: The ID of the property to update.
        key: Property key.
        value: New property value.
        version_number: Current version number of the property (incremented automatically).
    """
    require_str(space_id, "space_id")
    require_str(property_id, "property_id")
    require_str(key, "key")
    if version_number < 1:
        raise ValueError("'version_number' must be >= 1.")
    return request(
        "PUT",
        v2(f"/spaces/{space_id}/properties/{property_id}"),
        json={"key": key, "value": value, "version": {"number": version_number}},
    )


@mcp.tool(title="Delete Space Property", annotations=_DESTROY)
def delete_space_property(space_id: str, property_id: str) -> Any:
    """Delete a content property from a space.

    Args:
        space_id: The ID of the space.
        property_id: The ID of the property to delete.
    """
    require_str(space_id, "space_id")
    require_str(property_id, "property_id")
    return request("DELETE", v2(f"/spaces/{space_id}/properties/{property_id}"))


# ===========================================================================
# Pages — extended (bulk get + update title)
# ===========================================================================


@mcp.tool(title="Bulk Get Pages", annotations=_READ_ONLY)
def bulk_get_pages(
    page_ids: list[str],
    body_format: Optional[str] = None,
) -> Any:
    """Fetch multiple pages by their IDs in a single request.

    Returns a results list with one entry per resolved page ID.

    Args:
        page_ids: List of page IDs to retrieve (up to 250).
        body_format: Body representation — 'storage', 'atlas_doc_format', or 'view'.
    """
    if not page_ids:
        raise ValueError("'page_ids' must be a non-empty list.")
    check_enum(body_format, "body_format", {"storage", "atlas_doc_format", "view"})
    return request(
        "GET",
        v2("/pages"),
        params=clean({"id": ",".join(page_ids), "body-format": body_format}),
    )


@mcp.tool(title="Update Page Title", annotations=_UPDATE)
def update_page_title(page_id: str, title: str) -> Any:
    """Rename a page without changing its body or version metadata.

    Args:
        page_id: The ID of the page to rename.
        title: The new title for the page.
    """
    require_str(page_id, "page_id")
    require_str(title, "title")
    return request(
        "PUT",
        v2(f"/pages/{page_id}/title"),
        json={"title": title},
    )


# ===========================================================================
# Labels — global (list all labels; list blogposts by label)
# ===========================================================================


@mcp.tool(title="List Labels", annotations=_READ_ONLY)
def list_labels(
    label_prefix: Optional[str] = None,
    body_format: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Any:
    """List labels across the entire Confluence instance.

    Args:
        label_prefix: Filter by prefix — 'global', 'my', or 'team'.
        body_format: Body representation for associated content.
        cursor: Pagination cursor from a previous response.
        limit: Max results to return (default 25, max 250).
    """
    check_enum(label_prefix, "label_prefix", {"global", "my", "team"})
    return request(
        "GET",
        v2("/labels"),
        params=clean(
            {
                "prefix": label_prefix,
                "body-format": body_format,
                "cursor": cursor,
                "limit": limit,
            }
        ),
    )


@mcp.tool(title="List Blogposts With Label", annotations=_READ_ONLY)
def list_blogposts_with_label(
    label_id: str,
    space_id: Optional[str] = None,
    body_format: Optional[str] = None,
    sort: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Any:
    """List blog posts that carry a specific label.

    Args:
        label_id: The ID of the label.
        space_id: Restrict results to this space ID.
        body_format: Body representation — 'storage', 'atlas_doc_format', or 'view'.
        sort: Sort order (e.g. 'created-date', '-created-date', 'title').
        cursor: Pagination cursor from a previous response.
        limit: Max results to return (default 25, max 250).
    """
    require_str(label_id, "label_id")
    return request(
        "GET",
        v2(f"/labels/{label_id}/blogposts"),
        params=clean(
            {
                "space-id": space_id,
                "body-format": body_format,
                "sort": sort,
                "cursor": cursor,
                "limit": limit,
            }
        ),
    )


# ===========================================================================
# Inline Comments — create
# ===========================================================================


@mcp.tool(title="Create Inline Comment", annotations=_CREATE)
def create_inline_comment(
    page_id: str,
    body_value: str,
    inline_marker_ref: str,
    body_representation: str = "storage",
    resolved: bool = False,
) -> Any:
    """Create an inline comment anchored to a text selection on a page.

    Args:
        page_id: The ID of the page to comment on.
        body_value: HTML/storage-format body of the comment.
        inline_marker_ref: The marker reference identifying the text selection
            (obtained from the page's inline marker data).
        body_representation: Body format — 'storage', 'wiki', or 'atlas_doc_format'.
        resolved: Whether to create the comment in a resolved state.
    """
    require_str(page_id, "page_id")
    require_str(body_value, "body_value")
    require_str(inline_marker_ref, "inline_marker_ref")
    check_enum(body_representation, "body_representation", _VALID_BODY_REPRESENTATIONS)
    return request(
        "POST",
        v2("/inline-comments"),
        json={
            "pageId": page_id,
            "body": {"representation": body_representation, "value": body_value},
            "inlineMarkerRef": inline_marker_ref,
            "resolved": resolved,
        },
    )


# ===========================================================================
# Blogposts — full CRUD
# ===========================================================================


@mcp.tool(title="List Blogposts", annotations=_READ_ONLY)
def list_blogposts(
    space_id: Optional[str] = None,
    status: Optional[str] = None,
    sort: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
) -> Any:
    """List blog posts, optionally filtered by space.

    Args:
        space_id: Restrict to this space ID.
        status: Filter by status — 'current' or 'draft'.
        sort: Sort order (e.g. 'created-date', '-created-date', 'title').
        cursor: Pagination cursor from a previous response.
        limit: Max results to return (default 25, max 250).
    """
    check_enum(status, "status", {"current", "draft"})
    return request(
        "GET",
        v2("/blogposts"),
        params=clean(
            {
                "space-id": space_id,
                "status": status,
                "sort": sort,
                "cursor": cursor,
                "limit": limit,
            }
        ),
    )


@mcp.tool(title="Get Blogpost", annotations=_READ_ONLY)
def get_blogpost(
    blogpost_id: str,
    body_format: Optional[str] = None,
    version: Optional[int] = None,
) -> Any:
    """Get a blog post by ID.

    Args:
        blogpost_id: The ID of the blog post.
        body_format: Body representation — 'storage', 'atlas_doc_format', or 'view'.
        version: Retrieve a specific historical version number.
    """
    require_str(blogpost_id, "blogpost_id")
    check_enum(body_format, "body_format", {"storage", "atlas_doc_format", "view"})
    return request(
        "GET",
        v2(f"/blogposts/{blogpost_id}"),
        params=clean({"body-format": body_format, "version": version}),
    )


@mcp.tool(title="Create Blogpost", annotations=_CREATE)
def create_blogpost(
    space_id: str,
    title: str,
    body_value: str,
    body_representation: str = "storage",
    status: str = "current",
) -> Any:
    """Create a new blog post in a space.

    Args:
        space_id: The ID of the space to publish in.
        title: Title of the blog post.
        body_value: HTML/storage body content.
        body_representation: Body format — 'storage', 'wiki', or 'atlas_doc_format'.
        status: 'current' to publish immediately, or 'draft' to save as draft.
    """
    require_str(space_id, "space_id")
    require_str(title, "title")
    check_enum(body_representation, "body_representation", _VALID_BODY_REPRESENTATIONS)
    check_enum(status, "status", {"current", "draft"})
    return request(
        "POST",
        v2("/blogposts"),
        json={
            "spaceId": space_id,
            "title": title,
            "body": {"representation": body_representation, "value": body_value},
            "status": status,
        },
    )


@mcp.tool(title="Update Blogpost", annotations=_UPDATE)
def update_blogpost(
    blogpost_id: str,
    title: str,
    body_value: str,
    version_number: int,
    body_representation: str = "storage",
    status: str = "current",
) -> Any:
    """Update an existing blog post.

    Args:
        blogpost_id: The ID of the blog post to update.
        title: New title.
        body_value: New body content.
        version_number: The *new* version number (current version + 1).
        body_representation: Body format — 'storage', 'wiki', or 'atlas_doc_format'.
        status: 'current' or 'draft'.
    """
    require_str(blogpost_id, "blogpost_id")
    require_str(title, "title")
    if version_number < 1:
        raise ValueError("'version_number' must be >= 1.")
    check_enum(body_representation, "body_representation", _VALID_BODY_REPRESENTATIONS)
    check_enum(status, "status", {"current", "draft"})
    return request(
        "PUT",
        v2(f"/blogposts/{blogpost_id}"),
        json={
            "id": blogpost_id,
            "title": title,
            "body": {"representation": body_representation, "value": body_value},
            "version": {"number": version_number},
            "status": status,
        },
    )


@mcp.tool(title="Delete Blogpost", annotations=_DESTROY)
def delete_blogpost(blogpost_id: str, purge: bool = False) -> Any:
    """Delete a blog post (moves to trash, or permanently purges).

    Args:
        blogpost_id: The ID of the blog post to delete.
        purge: If True, permanently delete instead of moving to trash.
    """
    require_str(blogpost_id, "blogpost_id")
    return request(
        "DELETE",
        v2(f"/blogposts/{blogpost_id}"),
        params={"purge": "true"} if purge else None,
    )


# ===========================================================================
# Bulk user lookup
# ===========================================================================


@mcp.tool(title="Bulk User Lookup", annotations=_READ_ONLY)
def bulk_user_lookup(
    account_ids: list[str],
) -> Any:
    """Resolve multiple Atlassian account IDs to user profiles in a single call.

    Useful when you have a list of assignee/author IDs from tasks or comments
    and want to retrieve display names and emails in bulk.

    Args:
        account_ids: List of Atlassian account IDs to look up (up to 200).
    """
    if not account_ids:
        raise ValueError("'account_ids' must be a non-empty list.")
    return request(
        "POST",
        v2("/users-bulk"),
        json={"accountIds": account_ids},
    )
