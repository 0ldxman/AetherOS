from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlparse
from xml.etree import ElementTree

import requests
from django.conf import settings
from django.core.cache import cache


logger = logging.getLogger(__name__)

DAV_NS = "DAV:"
OC_NS = "http://owncloud.org/ns"

ROOT_PATH = "AETHER"

# The cached path is always verified against Nextcloud (fileid check),
# so a long TTL is safe: a stale entry costs one extra request, nothing more.
PATH_CACHE_TTL = 60 * 60

PROPFIND_BODY = """<?xml version="1.0" encoding="UTF-8"?>
<d:propfind
    xmlns:d="DAV:"
    xmlns:oc="http://owncloud.org/ns"
>
    <d:prop>
        <d:resourcetype />
        <d:getcontentlength />
        <d:getlastmodified />
        <d:getetag />
        <oc:fileid />
    </d:prop>
</d:propfind>
"""


@dataclass
class NextcloudFile:
    file_id: str
    path: str
    filename: str
    is_directory: bool
    size: int | None = None
    etag: str | None = None
    last_modified: str | None = None


def _path_cache_key(file_id: str) -> str:
    return f"nextcloud:path:{file_id}"


class NextcloudClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password

    @classmethod
    def from_settings(cls) -> "NextcloudClient":
        return cls(
            base_url=settings.NEXTCLOUD_URL,
            username=settings.NEXTCLOUD_USERNAME,
            password=settings.NEXTCLOUD_APP_PASSWORD,
        )

    @property
    def webdav_url(self) -> str:
        username = quote(
            self.username,
            safe="",
        )

        return (
            f"{self.base_url}"
            f"/remote.php/dav/files/{username}/"
        )

    @property
    def _webdav_base_path(self) -> str:
        return unquote(
            urlparse(self.webdav_url).path
        ).rstrip("/")

    def request(
        self,
        method: str,
        path: str = "",
        **kwargs,
    ):
        path = path.strip("/")

        encoded_path = quote(
            path,
            safe="/:@",
        )

        url = self.webdav_url + encoded_path

        response = requests.request(
            method,
            url,
            auth=(
                self.username,
                self.password,
            ),
            timeout=30,
            **kwargs,
        )

        response.raise_for_status()

        return response

    # ------------------------------------------------------------------
    # PROPFIND parsing
    # ------------------------------------------------------------------

    def _parse_response_node(
        self,
        response_node,
    ) -> NextcloudFile | None:
        """Convert one <d:response> element into a NextcloudFile.

        Returns None for entries that cannot be represented
        (no fileid, or the WebDAV root itself).
        """
        href = response_node.find(
            f"{{{DAV_NS}}}href"
        )

        if href is None or not href.text:
            return None

        prop = response_node.find(
            f".//{{{DAV_NS}}}prop"
        )

        if prop is None:
            return None

        file_id = prop.find(
            f"{{{OC_NS}}}fileid"
        )

        if file_id is None or not file_id.text:
            return None

        resource_type = prop.find(
            f"{{{DAV_NS}}}resourcetype"
        )

        is_directory = (
            resource_type is not None
            and resource_type.find(
                f"{{{DAV_NS}}}collection"
            ) is not None
        )

        webdav_base = self._webdav_base_path

        href_path = unquote(
            urlparse(href.text).path
        ).rstrip("/")

        prefix = webdav_base + "/"

        if not href_path.startswith(prefix):
            return None

        relative_path = href_path[len(prefix):].strip("/")

        if not relative_path:
            return None

        filename = relative_path.rsplit("/", 1)[-1]

        size_node = prop.find(
            f"{{{DAV_NS}}}getcontentlength"
        )

        etag_node = prop.find(
            f"{{{DAV_NS}}}getetag"
        )

        modified_node = prop.find(
            f"{{{DAV_NS}}}getlastmodified"
        )

        size = None

        if size_node is not None and size_node.text:
            try:
                size = int(size_node.text)
            except ValueError:
                size = None

        return NextcloudFile(
            file_id=file_id.text,
            path="/" + relative_path,
            filename=filename,
            is_directory=is_directory,
            size=size,
            etag=(
                etag_node.text
                if etag_node is not None
                else None
            ),
            last_modified=(
                modified_node.text
                if modified_node is not None
                else None
            ),
        )

    def _propfind(
        self,
        path: str,
        depth: str,
    ) -> list[NextcloudFile]:
        response = self.request(
            "PROPFIND",
            path,
            headers={
                "Depth": depth,
                "Content-Type": "application/xml",
            },
            data=PROPFIND_BODY,
        )

        root = ElementTree.fromstring(
            response.content
        )

        items: list[NextcloudFile] = []

        for response_node in root.findall(
            f"{{{DAV_NS}}}response"
        ):
            item = self._parse_response_node(
                response_node
            )

            if item is not None:
                items.append(item)

        return items

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list(
        self,
        path: str = "",
    ) -> list[NextcloudFile]:
        path = path.strip("/")

        items = self._propfind(path, "1")

        # Depth: 1 also returns the requested collection itself.
        own_path = "/" + path if path else None

        result = [
            item
            for item in items
            if item.path.rstrip("/") != own_path
        ]

        result.sort(
            key=lambda item: (
                not item.is_directory,
                item.filename.lower(),
            )
        )

        return result

    def stat(
        self,
        path: str,
    ) -> NextcloudFile | None:
        """Return metadata for a single path, or None if it is missing."""
        try:
            items = self._propfind(path, "0")
        except requests.HTTPError as exc:
            if (
                exc.response is not None
                and exc.response.status_code == 404
            ):
                return None

            raise

        return items[0] if items else None

    def get_file_by_id(
        self,
        file_id: str,
    ) -> NextcloudFile | None:
        file_id = str(file_id)
        key = _path_cache_key(file_id)

        cached_path = cache.get(key)

        if cached_path:
            item = self.stat(cached_path)

            if item is not None and item.file_id == file_id:
                return item

            # Moved, deleted or replaced: forget the stale path.
            cache.delete(key)

        item = self._find_file(
            ROOT_PATH,
            file_id,
        )

        if item is not None:
            cache.set(
                key,
                item.path,
                PATH_CACHE_TTL,
            )

        return item

    def _find_file(
        self,
        path: str,
        file_id: str,
    ) -> NextcloudFile | None:
        for item in self.list(path):
            if item.file_id == file_id:
                return item

            if item.is_directory:
                found = self._find_file(
                    item.path,
                    file_id,
                )

                if found is not None:
                    return found

        return None

    def stream(
        self,
        path: str,
        headers: dict[str, str] | None = None,
    ):
        response = self.request(
            "GET",
            path,
            headers=headers or {},
            stream=True,
        )

        logger.debug(
            "Nextcloud stream: status=%s url=%s "
            "content_type=%s content_encoding=%s "
            "content_length=%s",
            response.status_code,
            response.url,
            response.headers.get("Content-Type"),
            response.headers.get("Content-Encoding"),
            response.headers.get("Content-Length"),
        )

        return response