from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, unquote, urlparse
from xml.etree import ElementTree

import requests
from django.conf import settings


DAV_NS = "DAV:"
OC_NS = "http://owncloud.org/ns"


@dataclass
class NextcloudFile:
    file_id: str
    path: str
    filename: str
    is_directory: bool
    size: int | None = None
    etag: str | None = None
    last_modified: str | None = None


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

    def list(
        self,
        path: str = "",
    ) -> list[NextcloudFile]:

        path = path.strip("/")

        response = self.request(
            "PROPFIND",
            path,
            headers={
                "Depth": "1",
                "Content-Type": "application/xml",
            },
            data="""<?xml version="1.0" encoding="UTF-8"?>
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
""",
        )

        root = ElementTree.fromstring(
            response.content
        )

        result: list[NextcloudFile] = []

        webdav_base = urlparse(
            self.webdav_url
        ).path

        webdav_base = unquote(
            webdav_base
        ).rstrip("/")

        requested_path = (
            webdav_base
            + (
                "/"
                + path
                if path
                else ""
            )
        ).rstrip("/")

        for response_node in root.findall(
            f"{{{DAV_NS}}}response"
        ):
            href = response_node.find(
                f"{{{DAV_NS}}}href"
            )

            if href is None or not href.text:
                continue

            prop = response_node.find(
                f".//{{{DAV_NS}}}prop"
            )

            if prop is None:
                continue

            file_id = prop.find(
                f"{{{OC_NS}}}fileid"
            )

            if file_id is None or not file_id.text:
                continue

            resource_type = prop.find(
                f"{{{DAV_NS}}}resourcetype"
            )

            is_directory = (
                resource_type is not None
                and resource_type.find(
                    f"{{{DAV_NS}}}collection"
                ) is not None
            )

            href_path = urlparse(
                href.text
            ).path

            href_path = unquote(
                href_path
            ).rstrip("/")

            if href_path == webdav_base:
                continue

            if href_path == requested_path:
                continue

            prefix = webdav_base + "/"

            if not href_path.startswith(prefix):
                continue

            relative_path = href_path[
                len(prefix):
            ]

            relative_path = relative_path.strip("/")

            if not relative_path:
                continue

            filename = relative_path.rsplit(
                "/",
                1,
            )[-1]

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

            if (
                size_node is not None
                and size_node.text
            ):
                try:
                    size = int(
                        size_node.text
                    )
                except ValueError:
                    size = None

            result.append(
                NextcloudFile(
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
            )

        result.sort(
            key=lambda item: (
                not item.is_directory,
                item.filename.lower(),
            )
        )

        return result

    def get_file_by_id(
        self,
        file_id: str,
    ) -> NextcloudFile | None:
        return self._find_file(
            "AETHER",
            file_id,
        )

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
        import logging

        logger = logging.getLogger(__name__)

        response = self.request(
            "GET",
            path,
            headers=headers or {},
            stream=True,
        )

        logger.warning(
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
