# confluence-mcp

An MCP server for administering [Atlassian Confluence Cloud](https://www.atlassian.com/software/confluence) wiki pages.
Built with [FastMCP](https://github.com/jlowin/fastmcp) and the Confluence REST API v2.

## Features

- Create, read, update, delete, and restore pages
- Move (reparent) pages within a space; transfer page ownership
- Navigate the page tree (children, ancestors, descendants)
- Bulk-fetch multiple pages in a single request
- Create, read, update, and delete spaces; manage space content properties
- Full blog post CRUD (create, read, update, delete)
- Read labels (list all labels, list pages/blogposts by label)
- Inspect version history
- Manage footer and inline comments (including creating inline comments)
- List and delete attachments
- Manage page and space content properties (key/value metadata)
- Manage tasks
- Bulk user lookup (resolve multiple account IDs to profiles)

## Requirements

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) package manager
- An Atlassian Confluence Cloud account with API access

## Setup

### 1. Clone and install

```bash
git clone <repo-url>
cd confluence
uv sync
```

### 2. Configure credentials

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `CONFLUENCE_BASE_URL` | Yes | Your Confluence base URL, e.g. `https://your-domain.atlassian.net` |
| `CONFLUENCE_EMAIL` | Basic Auth | Atlassian account email |
| `CONFLUENCE_API_TOKEN` | Basic Auth | [Atlassian API token](https://id.atlassian.com/manage-profile/security/api-tokens) |
| `CONFLUENCE_BEARER_TOKEN` | Bearer Auth | Personal Access Token (alternative to Basic Auth) |

Use either Basic Auth (`EMAIL` + `API_TOKEN`) or a Bearer token — not both.

### 3. Run

```bash
uv run confluence-mcp
```

The server communicates over stdio (standard MCP transport).

## Integration

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or the equivalent on your OS:

```json
{
  "mcpServers": {
    "confluence": {
      "command": "uv",
      "args": [
        "--directory", "/path/to/confluence",
        "run", "confluence-mcp"
      ],
      "env": {
        "CONFLUENCE_BASE_URL": "https://your-domain.atlassian.net",
        "CONFLUENCE_EMAIL": "you@example.com",
        "CONFLUENCE_API_TOKEN": "your-api-token"
      }
    }
  }
}
```

### OpenCode

Add to your OpenCode MCP config:

```json
{
  "confluence": {
    "command": "uv",
    "args": [
      "--directory", "/path/to/confluence",
      "run", "confluence-mcp"
    ]
  }
}
```

Set the env vars in your shell or `.env` file.

## Tool Reference

### Pages

| Tool | Description |
|---|---|
| `list_pages` | List pages filtered by space, title, status, or parent |
| `get_page` | Get a page by ID (with optional body format and version) |
| `bulk_get_pages` | Fetch multiple pages by ID in a single request |
| `create_page` | Create a new page in a space |
| `update_page` | Update content, title, parent (move), or owner of a page |
| `update_page_title` | Rename a page without changing its body or version metadata |
| `delete_page` | Move a page to trash (or permanently delete with `purge=true`) |
| `restore_page` | Restore a trashed page to `current` status |
| `get_page_operations` | List permitted operations for a page |

**Moving a page:** pass `parent_id` in `update_page` to reparent within the same space.
Cross-space moves are not supported by the Confluence v2 API.

**Transferring ownership:** pass `owner_id` (Atlassian account ID) in `update_page`.

### Page Navigation

| Tool | Description |
|---|---|
| `get_page_children` | All child pages (recursive, paginated) |
| `get_page_direct_children` | Immediate children only |
| `get_page_ancestors` | Full breadcrumb trail to the root |
| `get_page_descendants` | All descendants |

### Spaces

| Tool | Description |
|---|---|
| `list_spaces` | List spaces (filterable by type, status, key, label) |
| `get_space` | Get a space by ID |
| `create_space` | Create a new space |
| `get_space_operations` | List permitted operations for a space |
| `get_space_content_labels` | List all labels used on content within a space |
| `list_pages_in_space` | List pages in a space |
| `list_blogposts_in_space` | List blog posts in a space |
| `get_space_permissions` | List permission assignments for a space |

### Space Properties

| Tool | Description |
|---|---|
| `list_space_properties` | List key/value properties on a space |
| `get_space_property` | Get a specific space property |
| `create_space_property` | Create a new space property |
| `update_space_property` | Update an existing space property |
| `delete_space_property` | Delete a space property |

### Blog Posts

| Tool | Description |
|---|---|
| `list_blogposts` | List blog posts (filterable by space, status) |
| `get_blogpost` | Get a blog post by ID |
| `create_blogpost` | Create a new blog post in a space |
| `update_blogpost` | Update content, title, or status of a blog post |
| `delete_blogpost` | Move a blog post to trash (or permanently delete with `purge=true`) |

### Labels

> Label add/remove is available via the Confluence v1 API only; the v2 API is read-only for labels.

| Tool | Description |
|---|---|
| `list_labels` | List all labels across the Confluence instance |
| `list_page_labels` | Labels attached to a page |
| `list_space_labels` | Labels used across a space |
| `list_pages_with_label` | Pages that carry a specific label |
| `list_blogposts_with_label` | Blog posts that carry a specific label |

### Version History

| Tool | Description |
|---|---|
| `list_page_versions` | Version history of a page |
| `get_page_version` | Details of a specific page version |

### Footer Comments

| Tool | Description |
|---|---|
| `list_page_footer_comments` | Footer comments on a page |
| `get_footer_comment` | Get a footer comment by ID |
| `create_footer_comment` | Create a comment on a page, blog post, or as a reply |
| `update_footer_comment` | Update comment content |
| `delete_footer_comment` | Delete a comment |
| `list_footer_comment_replies` | List replies to a comment |

### Inline Comments

| Tool | Description |
|---|---|
| `list_page_inline_comments` | Inline comments on a page |
| `get_inline_comment` | Get an inline comment by ID |
| `create_inline_comment` | Create an inline comment anchored to a text selection |
| `update_inline_comment` | Update content or resolved state |
| `delete_inline_comment` | Delete an inline comment |

### Attachments

| Tool | Description |
|---|---|
| `list_page_attachments` | List attachments on a page |
| `get_attachment` | Get an attachment by ID |
| `delete_attachment` | Delete an attachment |

> Uploading attachments requires multipart form data and is not supported by this server.

### Content Properties

| Tool | Description |
|---|---|
| `list_page_properties` | List key/value properties on a page |
| `get_page_property` | Get a specific property |
| `create_page_property` | Create a new property |
| `update_page_property` | Update an existing property |
| `delete_page_property` | Delete a property |

### Tasks

| Tool | Description |
|---|---|
| `list_tasks` | List tasks (filterable by status, space, page, assignee) |
| `get_task` | Get a task by ID |
| `update_task` | Update task status, assignee, or due date |

### Utility

| Tool | Description |
|---|---|
| `convert_ids_to_types` | Resolve content IDs to their types (page, blogpost, etc.) |
| `bulk_user_lookup` | Resolve multiple Atlassian account IDs to user profiles |

## Notes

- **Body formats:** `storage` (XHTML, default for write), `wiki` (Confluence wiki markup), `atlas_doc_format` (Atlassian Document Format / ADF), `view` (rendered HTML, read-only).
- **Versioning:** `update_page`, `update_blogpost`, `update_footer_comment`, and `update_inline_comment` all require passing the current `version_number`. The API increments it automatically. Always call `get_page` / `get_blogpost` first to obtain the current version.
- **Labels:** To add or remove labels, use the Confluence v1 REST API (`/wiki/rest/api/content/{id}/label`) directly — this is not exposed in this server.
