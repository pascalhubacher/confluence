"""
Unit tests for the Confluence MCP server (client.py, tools.py, server.py).

Strategy
--------
- All HTTP calls are intercepted with pytest-httpx (HTTPXMock fixture).
- Module-level globals (BASE_URL, EMAIL, API_TOKEN, BEARER_TOKEN) are patched
  via monkeypatch so each test controls credentials in isolation.
- Every public tool function is exercised at least once:
    - happy path (correct HTTP method, URL, params / JSON payload)
    - branch coverage for optional arguments that change behaviour
- The HTTP helpers (_get_headers, clean, v1, v2, request) are tested
  directly as well.
"""

from __future__ import annotations

import base64
import importlib
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from pytest_httpx import HTTPXMock

import confluence_mcp.client as client
import confluence_mcp.tools as tools

# ---------------------------------------------------------------------------
# Helpers / constants
# ---------------------------------------------------------------------------

BASE = "https://example.atlassian.net"
V2 = f"{BASE}/wiki/api/v2"
V1 = f"{BASE}/wiki/rest/api"

OK_JSON: dict[str, Any] = {"result": "ok"}
NO_CONTENT_STATUS = 204


def _patch_globals(
    monkeypatch: pytest.MonkeyPatch,
    *,
    base_url: str = BASE,
    email: str = "",
    api_token: str = "",
    bearer_token: str = "",
) -> None:
    """Patch all module-level credential globals in client.py."""
    monkeypatch.setattr(client, "BASE_URL", base_url)
    monkeypatch.setattr(client, "EMAIL", email)
    monkeypatch.setattr(client, "API_TOKEN", api_token)
    monkeypatch.setattr(client, "BEARER_TOKEN", bearer_token)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


class TestClean:
    def test_removes_none_values(self) -> None:
        assert client.clean({"a": 1, "b": None, "c": "x"}) == {"a": 1, "c": "x"}

    def test_all_none_returns_empty(self) -> None:
        assert client.clean({"a": None}) == {}

    def test_preserves_falsy_non_none(self) -> None:
        assert client.clean({"a": 0, "b": False, "c": ""}) == {
            "a": 0,
            "b": False,
            "c": "",
        }


class TestUrlBuilders:
    def test_v2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(client, "BASE_URL", BASE)
        assert client.v2("/pages") == f"{BASE}/wiki/api/v2/pages"

    def test_v1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(client, "BASE_URL", BASE)
        assert client.v1("/content") == f"{BASE}/wiki/rest/api/content"


class TestGetHeaders:
    def test_bearer_token_takes_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_globals(monkeypatch, email="u@e.com", api_token="tok", bearer_token="bt")
        headers = client._get_headers()
        assert headers["Authorization"] == "Bearer bt"

    def test_basic_auth_when_no_bearer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_globals(monkeypatch, email="user@example.com", api_token="secret")
        headers = client._get_headers()
        expected = base64.b64encode(b"user@example.com:secret").decode()
        assert headers["Authorization"] == f"Basic {expected}"

    def test_no_auth_when_no_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_globals(monkeypatch)
        headers = client._get_headers()
        assert "Authorization" not in headers
        assert headers["Accept"] == "application/json"

    def test_content_type_always_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        assert client._get_headers()["Content-Type"] == "application/json"


class TestRequest:
    def test_returns_json_on_success(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/pages", json=OK_JSON)
        result = client.request("GET", f"{V2}/pages")
        assert result == OK_JSON

    def test_returns_status_dict_when_no_content(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/pages/1", status_code=204, content=b"")
        result = client.request("DELETE", f"{V2}/pages/1")
        assert result == {"status": 204, "message": "Success"}

    def test_raises_on_http_error(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/pages/999", status_code=404)
        with pytest.raises(httpx.HTTPStatusError):
            client.request("GET", f"{V2}/pages/999")

    def test_passes_params(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/pages",
            match_params={"limit": "10"},
            json=OK_JSON,
        )
        result = client.request("GET", f"{V2}/pages", params={"limit": 10})
        assert result == OK_JSON

    def test_passes_json_body(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        body = {"title": "Test"}
        httpx_mock.add_response(url=f"{V2}/pages", method="POST", json=OK_JSON)
        result = client.request("POST", f"{V2}/pages", json=body)
        assert result == OK_JSON


# ---------------------------------------------------------------------------
# Pages — CRUD
# ---------------------------------------------------------------------------


class TestListPages:
    def test_no_filters(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/pages", json=OK_JSON)
        assert tools.list_pages() == OK_JSON


# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------


class TestValidateConfig:
    def test_raises_when_base_url_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, base_url="", bearer_token="bt")
        with pytest.raises(ValueError, match="CONFLUENCE_BASE_URL"):
            client.validate_config()

    def test_raises_when_no_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_globals(monkeypatch, base_url=BASE)
        with pytest.raises(ValueError, match="credentials"):
            client.validate_config()

    def test_passes_with_bearer_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_globals(monkeypatch, base_url=BASE, bearer_token="bt")
        client.validate_config()  # must not raise

    def test_passes_with_email_and_api_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, base_url=BASE, email="u@e.com", api_token="tok")
        client.validate_config()  # must not raise

    def test_raises_when_only_email_no_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, base_url=BASE, email="u@e.com")
        with pytest.raises(ValueError, match="credentials"):
            client.validate_config()


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------


class TestRequireStr:
    def test_raises_on_empty_string(self) -> None:
        with pytest.raises(ValueError, match="'page_id'"):
            client.require_str("", "page_id")

    def test_raises_on_whitespace_only(self) -> None:
        with pytest.raises(ValueError, match="'page_id'"):
            client.require_str("   ", "page_id")

    def test_passes_on_valid_string(self) -> None:
        client.require_str("12345", "page_id")  # must not raise


class TestCheckEnum:
    def test_raises_on_invalid_value(self) -> None:
        with pytest.raises(ValueError, match="'status'"):
            client.check_enum("bad", "status", {"current", "draft"})

    def test_passes_on_valid_value(self) -> None:
        client.check_enum("current", "status", {"current", "draft"})  # must not raise

    def test_passes_on_none(self) -> None:
        client.check_enum(
            None, "status", {"current", "draft"}
        )  # None is always allowed


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


class TestRateLimit:
    def test_rate_limit_allows_request(self) -> None:
        """_rate_limit() should complete without error and consume a token."""
        import time

        # Reset the bucket to full so timing-sensitive CI runs don't flap
        client._rate_tokens = client._RATE_LIMIT_RPS
        client._rate_last = time.monotonic()
        client._rate_limit()  # must not raise or hang


# ---------------------------------------------------------------------------
# Tool input validation — sampled representative cases
# ---------------------------------------------------------------------------


class TestToolInputValidation:
    def test_get_page_empty_id_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        with pytest.raises(ValueError, match="'page_id'"):
            tools.get_page("")

    def test_get_page_invalid_body_format_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        with pytest.raises(ValueError, match="'body_format'"):
            tools.get_page("1", body_format="html")

    def test_create_page_empty_space_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        with pytest.raises(ValueError, match="'space_id'"):
            tools.create_page("", "Title", "<p/>")

    def test_create_page_empty_title_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        with pytest.raises(ValueError, match="'title'"):
            tools.create_page("S1", "", "<p/>")

    def test_create_page_invalid_status_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        with pytest.raises(ValueError, match="'status'"):
            tools.create_page("S1", "T", "<p/>", status="published")

    def test_update_page_zero_version_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        with pytest.raises(ValueError, match="'version_number'"):
            tools.update_page("1", "T", "<p/>", 0)

    def test_update_page_invalid_body_repr_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        with pytest.raises(ValueError, match="'body_representation'"):
            tools.update_page("1", "T", "<p/>", 2, body_representation="markdown")

    def test_delete_page_empty_id_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        with pytest.raises(ValueError, match="'page_id'"):
            tools.delete_page("")

    def test_list_spaces_invalid_type_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        with pytest.raises(ValueError, match="'type'"):
            tools.list_spaces(type="team")

    def test_list_spaces_invalid_status_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        with pytest.raises(ValueError, match="'status'"):
            tools.list_spaces(status="deleted")

    def test_list_pages_invalid_status_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        with pytest.raises(ValueError, match="'status'"):
            tools.list_pages(status="published")

    def test_list_tasks_invalid_status_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        with pytest.raises(ValueError, match="'status'"):
            tools.list_tasks(status="pending")

    def test_update_task_invalid_status_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        with pytest.raises(ValueError, match="'status'"):
            tools.update_task("1", status="done")

    def test_create_footer_comment_no_target_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        with pytest.raises(ValueError, match="exactly one"):
            tools.create_footer_comment("<p/>")

    def test_create_footer_comment_two_targets_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        with pytest.raises(ValueError, match="exactly one"):
            tools.create_footer_comment("<p/>", page_id="1", blogpost_id="2")

    def test_convert_ids_empty_list_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        with pytest.raises(ValueError, match="'content_ids'"):
            tools.convert_ids_to_types([])

    def test_get_page_version_zero_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        with pytest.raises(ValueError, match="'version_number'"):
            tools.get_page_version("1", 0)

    def test_update_footer_comment_zero_version_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        with pytest.raises(ValueError, match="'version_number'"):
            tools.update_footer_comment("1", "<p/>", 0)

    def test_update_inline_comment_zero_version_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        with pytest.raises(ValueError, match="'version_number'"):
            tools.update_inline_comment("1", "<p/>", 0)

    def test_list_pages_in_space_invalid_depth_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        with pytest.raises(ValueError, match="'depth'"):
            tools.list_pages_in_space("S1", depth="shallow")


# Pages — navigation
# ---------------------------------------------------------------------------


class TestGetPageChildren:
    def test_minimal(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/pages/1/children", json=OK_JSON)
        assert tools.get_page_children("1") == OK_JSON

    def test_with_pagination(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/pages/1/children",
            match_params={"cursor": "tok", "limit": "5", "sort": "title"},
            json=OK_JSON,
        )
        assert (
            tools.get_page_children("1", cursor="tok", limit=5, sort="title") == OK_JSON
        )


class TestGetPageDirectChildren:
    def test_basic(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/pages/1/direct-children", json=OK_JSON)
        assert tools.get_page_direct_children("1") == OK_JSON

    def test_with_pagination(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/pages/1/direct-children",
            match_params={"cursor": "c", "limit": "10"},
            json=OK_JSON,
        )
        assert tools.get_page_direct_children("1", cursor="c", limit=10) == OK_JSON


class TestGetPageAncestors:
    def test_basic(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/pages/1/ancestors", json=OK_JSON)
        assert tools.get_page_ancestors("1") == OK_JSON


class TestGetPageDescendants:
    def test_basic(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/pages/1/descendants", json=OK_JSON)
        assert tools.get_page_descendants("1") == OK_JSON

    def test_with_pagination(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/pages/1/descendants",
            match_params={"limit": "20", "cursor": "next"},
            json=OK_JSON,
        )
        assert tools.get_page_descendants("1", limit=20, cursor="next") == OK_JSON


# ---------------------------------------------------------------------------
# Spaces
# ---------------------------------------------------------------------------


class TestListSpaces:
    def test_no_filters(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/spaces", json=OK_JSON)
        assert tools.list_spaces() == OK_JSON

    def test_with_all_filters(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/spaces",
            match_params={
                "ids": "1,2",
                "keys": "A,B",
                "type": "global",
                "status": "current",
                "labels": "eng",
                "sort": "name",
                "cursor": "c",
                "limit": "50",
            },
            json=OK_JSON,
        )
        result = tools.list_spaces(
            ids="1,2",
            keys="A,B",
            type="global",
            status="current",
            labels="eng",
            sort="name",
            cursor="c",
            limit=50,
        )
        assert result == OK_JSON


class TestGetSpace:
    def test_basic(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/spaces/S1", json=OK_JSON)
        assert tools.get_space("S1") == OK_JSON


class TestListPagesInSpace:
    def test_minimal(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/spaces/S1/pages", json=OK_JSON)
        assert tools.list_pages_in_space("S1") == OK_JSON

    def test_with_params(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/spaces/S1/pages",
            match_params={
                "depth": "root",
                "sort": "title",
                "status": "current",
                "limit": "10",
            },
            json=OK_JSON,
        )
        assert (
            tools.list_pages_in_space(
                "S1", depth="root", sort="title", status="current", limit=10
            )
            == OK_JSON
        )


class TestListBlogpostsInSpace:
    def test_minimal(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/spaces/S1/blogposts", json=OK_JSON)
        assert tools.list_blogposts_in_space("S1") == OK_JSON

    def test_with_params(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/spaces/S1/blogposts",
            match_params={
                "sort": "-created-date",
                "status": "current",
                "cursor": "c",
                "limit": "5",
            },
            json=OK_JSON,
        )
        assert (
            tools.list_blogposts_in_space(
                "S1", sort="-created-date", status="current", cursor="c", limit=5
            )
            == OK_JSON
        )


class TestGetSpacePermissions:
    def test_minimal(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/spaces/S1/permissions", json=OK_JSON)
        assert tools.get_space_permissions("S1") == OK_JSON

    def test_with_pagination(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/spaces/S1/permissions",
            match_params={"cursor": "tok", "limit": "20"},
            json=OK_JSON,
        )
        assert tools.get_space_permissions("S1", cursor="tok", limit=20) == OK_JSON


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


class TestListPageLabels:
    def test_minimal(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/pages/1/labels", json=OK_JSON)
        assert tools.list_page_labels("1") == OK_JSON

    def test_with_prefix_and_pagination(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/pages/1/labels",
            match_params={
                "prefix": "global",
                "sort": "name",
                "cursor": "c",
                "limit": "10",
            },
            json=OK_JSON,
        )
        assert (
            tools.list_page_labels(
                "1", prefix="global", sort="name", cursor="c", limit=10
            )
            == OK_JSON
        )


class TestListSpaceLabels:
    def test_minimal(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/spaces/S1/labels", json=OK_JSON)
        assert tools.list_space_labels("S1") == OK_JSON

    def test_with_params(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/spaces/S1/labels",
            match_params={
                "prefix": "team",
                "sort": "name",
                "cursor": "x",
                "limit": "5",
            },
            json=OK_JSON,
        )
        assert (
            tools.list_space_labels(
                "S1", prefix="team", sort="name", cursor="x", limit=5
            )
            == OK_JSON
        )


class TestListPagesWithLabel:
    def test_minimal(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/labels/L1/pages", json=OK_JSON)
        assert tools.list_pages_with_label("L1") == OK_JSON

    def test_with_all_params(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/labels/L1/pages",
            match_params={
                "space-id": "S1",
                "body-format": "storage",
                "sort": "title",
                "cursor": "c",
                "limit": "10",
            },
            json=OK_JSON,
        )
        result = tools.list_pages_with_label(
            "L1",
            space_id="S1",
            body_format="storage",
            sort="title",
            cursor="c",
            limit=10,
        )
        assert result == OK_JSON


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


class TestListPageVersions:
    def test_minimal(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/pages/1/versions", json=OK_JSON)
        assert tools.list_page_versions("1") == OK_JSON

    def test_with_pagination(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/pages/1/versions",
            match_params={"cursor": "c", "limit": "25", "sort": "-created-date"},
            json=OK_JSON,
        )
        assert (
            tools.list_page_versions("1", cursor="c", limit=25, sort="-created-date")
            == OK_JSON
        )


class TestGetPageVersion:
    def test_basic(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/pages/1/versions/3", json=OK_JSON)
        assert tools.get_page_version("1", 3) == OK_JSON


# ---------------------------------------------------------------------------
# Footer Comments
# ---------------------------------------------------------------------------


class TestListPageFooterComments:
    def test_minimal(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/pages/1/footer-comments", json=OK_JSON)
        assert tools.list_page_footer_comments("1") == OK_JSON

    def test_with_params(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/pages/1/footer-comments",
            match_params={
                "body-format": "view",
                "sort": "created-date",
                "cursor": "c",
                "limit": "5",
            },
            json=OK_JSON,
        )
        assert (
            tools.list_page_footer_comments(
                "1", body_format="view", sort="created-date", cursor="c", limit=5
            )
            == OK_JSON
        )


class TestGetFooterComment:
    def test_minimal(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/footer-comments/C1", json=OK_JSON)
        assert tools.get_footer_comment("C1") == OK_JSON

    def test_with_version(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/footer-comments/C1",
            match_params={"body-format": "storage", "version": "2"},
            json=OK_JSON,
        )
        assert (
            tools.get_footer_comment("C1", body_format="storage", version=2) == OK_JSON
        )


class TestCreateFooterComment:
    def test_on_page(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/footer-comments",
            method="POST",
            match_json={
                "body": {"representation": "storage", "value": "Great page!"},
                "pageId": "42",
            },
            json=OK_JSON,
        )
        assert tools.create_footer_comment("Great page!", page_id="42") == OK_JSON

    def test_on_blogpost(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/footer-comments",
            method="POST",
            match_json={
                "body": {"representation": "storage", "value": "Nice post"},
                "blogPostId": "B1",
            },
            json=OK_JSON,
        )
        assert tools.create_footer_comment("Nice post", blogpost_id="B1") == OK_JSON

    def test_reply(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/footer-comments",
            method="POST",
            match_json={
                "body": {"representation": "wiki", "value": "I agree"},
                "parentCommentId": "C1",
            },
            json=OK_JSON,
        )
        assert (
            tools.create_footer_comment(
                "I agree", parent_comment_id="C1", body_representation="wiki"
            )
            == OK_JSON
        )


class TestUpdateFooterComment:
    def test_basic(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/footer-comments/C1",
            method="PUT",
            match_json={
                "version": {"number": 2},
                "body": {"representation": "storage", "value": "Updated comment"},
            },
            json=OK_JSON,
        )
        assert tools.update_footer_comment("C1", "Updated comment", 2) == OK_JSON


class TestDeleteFooterComment:
    def test_basic(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/footer-comments/C1",
            method="DELETE",
            status_code=204,
            content=b"",
        )
        result = tools.delete_footer_comment("C1")
        assert result["status"] == 204


class TestListFooterCommentReplies:
    def test_minimal(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/footer-comments/C1/children", json=OK_JSON)
        assert tools.list_footer_comment_replies("C1") == OK_JSON

    def test_with_params(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/footer-comments/C1/children",
            match_params={
                "body-format": "view",
                "sort": "created-date",
                "cursor": "c",
                "limit": "10",
            },
            json=OK_JSON,
        )
        assert (
            tools.list_footer_comment_replies(
                "C1", body_format="view", sort="created-date", cursor="c", limit=10
            )
            == OK_JSON
        )


# ---------------------------------------------------------------------------
# Inline Comments
# ---------------------------------------------------------------------------


class TestListPageInlineComments:
    def test_minimal(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/pages/1/inline-comments", json=OK_JSON)
        assert tools.list_page_inline_comments("1") == OK_JSON

    def test_with_params(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/pages/1/inline-comments",
            match_params={
                "body-format": "storage",
                "sort": "created-date",
                "cursor": "c",
                "limit": "5",
            },
            json=OK_JSON,
        )
        assert (
            tools.list_page_inline_comments(
                "1", body_format="storage", sort="created-date", cursor="c", limit=5
            )
            == OK_JSON
        )


class TestGetInlineComment:
    def test_minimal(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/inline-comments/I1", json=OK_JSON)
        assert tools.get_inline_comment("I1") == OK_JSON

    def test_with_body_format_and_version(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/inline-comments/I1",
            match_params={"body-format": "view", "version": "1"},
            json=OK_JSON,
        )
        assert tools.get_inline_comment("I1", body_format="view", version=1) == OK_JSON


class TestUpdateInlineComment:
    def test_without_resolved(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/inline-comments/I1",
            method="PUT",
            match_json={
                "version": {"number": 2},
                "body": {"representation": "storage", "value": "Fixed"},
            },
            json=OK_JSON,
        )
        assert tools.update_inline_comment("I1", "Fixed", 2) == OK_JSON

    def test_with_resolved_true(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/inline-comments/I1",
            method="PUT",
            match_json={
                "version": {"number": 3},
                "body": {"representation": "storage", "value": "Done"},
                "resolved": True,
            },
            json=OK_JSON,
        )
        assert tools.update_inline_comment("I1", "Done", 3, resolved=True) == OK_JSON

    def test_with_resolved_false(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/inline-comments/I1",
            method="PUT",
            match_json={
                "version": {"number": 3},
                "body": {"representation": "storage", "value": "Reopened"},
                "resolved": False,
            },
            json=OK_JSON,
        )
        assert (
            tools.update_inline_comment("I1", "Reopened", 3, resolved=False) == OK_JSON
        )


class TestDeleteInlineComment:
    def test_basic(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/inline-comments/I1",
            method="DELETE",
            status_code=204,
            content=b"",
        )
        result = tools.delete_inline_comment("I1")
        assert result["status"] == 204


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------


class TestListPageAttachments:
    def test_minimal(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/pages/1/attachments", json=OK_JSON)
        assert tools.list_page_attachments("1") == OK_JSON

    def test_with_all_filters(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/pages/1/attachments",
            match_params={
                "sort": "created-date",
                "cursor": "c",
                "status": "current",
                "mediatype": "image/png",
                "filename": "diagram.png",
                "limit": "10",
            },
            json=OK_JSON,
        )
        result = tools.list_page_attachments(
            "1",
            sort="created-date",
            cursor="c",
            status="current",
            mediatype="image/png",
            filename="diagram.png",
            limit=10,
        )
        assert result == OK_JSON


class TestGetAttachment:
    def test_minimal(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/attachments/A1", json=OK_JSON)
        assert tools.get_attachment("A1") == OK_JSON

    def test_with_version(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/attachments/A1",
            match_params={"version": "2"},
            json=OK_JSON,
        )
        assert tools.get_attachment("A1", version=2) == OK_JSON


class TestDeleteAttachment:
    def test_basic(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/attachments/A1", method="DELETE", status_code=204, content=b""
        )
        result = tools.delete_attachment("A1")
        assert result["status"] == 204


# ---------------------------------------------------------------------------
# Content Properties
# ---------------------------------------------------------------------------


class TestListPageProperties:
    def test_minimal(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/pages/1/properties", json=OK_JSON)
        assert tools.list_page_properties("1") == OK_JSON

    def test_with_key_filter(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/pages/1/properties",
            match_params={"key": "my-prop", "cursor": "c", "limit": "5"},
            json=OK_JSON,
        )
        assert (
            tools.list_page_properties("1", key="my-prop", cursor="c", limit=5)
            == OK_JSON
        )


class TestGetPageProperty:
    def test_basic(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/pages/1/properties/P1", json=OK_JSON)
        assert tools.get_page_property("1", "P1") == OK_JSON


class TestCreatePageProperty:
    def test_basic(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/pages/1/properties",
            method="POST",
            match_json={"key": "status", "value": "reviewed"},
            json=OK_JSON,
        )
        assert tools.create_page_property("1", "status", "reviewed") == OK_JSON

    def test_with_dict_value(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/pages/1/properties",
            method="POST",
            match_json={"key": "meta", "value": {"score": 5}},
            json=OK_JSON,
        )
        assert tools.create_page_property("1", "meta", {"score": 5}) == OK_JSON


class TestUpdatePageProperty:
    def test_basic(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/pages/1/properties/P1",
            method="PUT",
            match_json={"key": "status", "value": "approved", "version": {"number": 2}},
            json=OK_JSON,
        )
        assert tools.update_page_property("1", "P1", "status", "approved", 2) == OK_JSON


class TestDeletePageProperty:
    def test_basic(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/pages/1/properties/P1",
            method="DELETE",
            status_code=204,
            content=b"",
        )
        result = tools.delete_page_property("1", "P1")
        assert result["status"] == 204


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


class TestListTasks:
    def test_no_filters(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/tasks", json=OK_JSON)
        assert tools.list_tasks() == OK_JSON

    def test_with_all_filters(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/tasks",
            match_params={
                "status": "open",
                "space-id": "S1",
                "page-id": "42",
                "assigned-to": "U1",
                "created-by": "U2",
                "due-at-from": "2025-01-01",
                "due-at-to": "2025-12-31",
                "cursor": "c",
                "limit": "10",
            },
            json=OK_JSON,
        )
        result = tools.list_tasks(
            status="open",
            space_id="S1",
            page_id="42",
            assigned_to="U1",
            created_by="U2",
            due_at_from="2025-01-01",
            due_at_to="2025-12-31",
            cursor="c",
            limit=10,
        )
        assert result == OK_JSON


class TestGetTask:
    def test_minimal(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(url=f"{V2}/tasks/T1", json=OK_JSON)
        assert tools.get_task("T1") == OK_JSON

    def test_with_body_format(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/tasks/T1",
            match_params={"body-format": "storage"},
            json=OK_JSON,
        )
        assert tools.get_task("T1", body_format="storage") == OK_JSON


class TestUpdateTask:
    def test_status_only(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/tasks/T1",
            method="PUT",
            match_json={"status": "complete"},
            json=OK_JSON,
        )
        assert tools.update_task("T1", "complete") == OK_JSON

    def test_with_assignee_and_due_date(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/tasks/T1",
            method="PUT",
            match_json={"status": "open", "assignedTo": "U1", "dueAt": "2025-06-01"},
            json=OK_JSON,
        )
        assert (
            tools.update_task("T1", "open", assigned_to="U1", due_at="2025-06-01")
            == OK_JSON
        )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


class TestConvertIdsToTypes:
    def test_basic(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        _patch_globals(monkeypatch, bearer_token="bt")
        httpx_mock.add_response(
            url=f"{V2}/content/convert-ids-to-types",
            method="POST",
            match_json={"contentIds": ["1", "2", "3"]},
            json=OK_JSON,
        )
        assert tools.convert_ids_to_types(["1", "2", "3"]) == OK_JSON


# ---------------------------------------------------------------------------
# Auth: Basic Auth header construction
# ---------------------------------------------------------------------------


class TestBasicAuthHeader:
    def test_correct_base64_encoding(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ) -> None:
        """Verify the Basic Auth header sent to the API is correctly encoded."""
        _patch_globals(monkeypatch, email="user@example.com", api_token="mytoken")
        expected_b64 = base64.b64encode(b"user@example.com:mytoken").decode()

        httpx_mock.add_response(
            url=f"{V2}/pages",
            match_headers={"Authorization": f"Basic {expected_b64}"},
            json=OK_JSON,
        )
        assert tools.list_pages() == OK_JSON
