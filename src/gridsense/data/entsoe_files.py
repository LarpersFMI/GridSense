"""Mirror monthly CSV extracts from the ENTSO-E Transparency Platform File Library (no API token).

Logs in with your Transparency Platform email and password from ENTSOE_USER and ENTSOE_PASSWORD
(environment or the repo's .env) and keeps only Romanian rows of each monthly file.
"""

import argparse
import io
import json
import logging
import os
import re
import tempfile
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

from gridsense import config

FILES_URL = "https://fms.tp.entsoe.eu/"
TOKEN_URL = "https://keycloak.tp.entsoe.eu/realms/tp/protocol/openid-connect/token"
ROOT = "/TP_export/"
MONTHLY_FILE = re.compile(r"^(\d{4})_(\d{2})_.+\.csv$")
MONTH = re.compile(r"^\d{4}-\d{2}$")
FOLDER = re.compile(r"^[\w.\-]+$")
AREA_COLUMNS = {"areamapcode", "mapcode", "areacode"}
MANIFEST = "_manifest.json"
LOGGER = logging.getLogger(__name__)


def select_monthly(names, first: str, last: str) -> list[str]:
    """Monthly extract names (YYYY_MM_<dataset>.csv) whose month lies in [first, last]."""
    selected = []
    for name in names:
        match = MONTHLY_FILE.match(name)
        if match and first <= f"{match[1]}-{match[2]}" <= last:
            selected.append(name)
    return sorted(selected)


def romanian_rows(payload: bytes, name: str) -> pd.DataFrame:
    """Rows of one tab-separated extract whose area is Romania, all values kept as text."""
    df = pd.read_csv(
        io.BytesIO(payload), sep="\t", dtype=str, encoding="utf-8-sig", keep_default_na=False
    )
    areas = [c for c in df.columns if re.sub(r"[^a-z]", "", c.lower()) in AREA_COLUMNS]
    if not areas:
        raise ValueError(f"{name}: no area column; found {list(df.columns)}")
    return df[df[areas].isin(["RO", config.BIDDING_ZONE]).any(axis=1)]


class FileLibrary:
    def __init__(self, session: requests.Session, username: str, password: str):
        self.session, self.username, self.password = session, username, password
        self.token, self.expires = "", 0.0

    def _headers(self) -> dict:
        if time.monotonic() >= self.expires:
            response = self.session.post(
                TOKEN_URL,
                data={
                    "client_id": "tp-fms-public",
                    "grant_type": "password",
                    "username": self.username,
                    "password": self.password,
                },
                timeout=30,
            )
            if response.status_code in (400, 401):
                raise ValueError("File Library login refused; check ENTSOE_USER/ENTSOE_PASSWORD")
            response.raise_for_status()
            data = response.json()
            self.token = data["access_token"]
            self.expires = time.monotonic() + data["expires_in"] - 30
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def _post(self, endpoint: str, body: dict) -> requests.Response:
        for attempt in range(3):
            try:
                response = self.session.post(
                    FILES_URL + endpoint,
                    data=json.dumps(body),
                    headers=self._headers(),
                    timeout=(10, 300),
                )
                if response.status_code < 500 or attempt == 2:
                    response.raise_for_status()
                    return response
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 2:
                    raise
            LOGGER.info("Retrying %s after a timeout or server error", endpoint)
            time.sleep(5 * 2**attempt)
        raise AssertionError("unreachable")

    def list_folder(self, folder: str) -> dict[str, str]:
        """File name -> last update timestamp."""
        body = {"path": f"{ROOT}{folder}/", "sorterList": [], "pageInfo": {"pageIndex": 0, "pageSize": 5000}}
        items = self._post("listFolder", body).json()["contentItemList"]
        return {x["name"]: str(x.get("lastUpdatedTimestamp")) for x in items}

    def download(self, folder: str, name: str) -> bytes:
        body = {
            "folder": f"{ROOT}{folder}/",
            "filename": name,
            "downloadAsZip": True,
            "topLevelFolder": ROOT.strip("/"),
        }
        with zipfile.ZipFile(io.BytesIO(self._post("downloadFileContent", body).content)) as zf:
            return zf.read(zf.infolist()[0])


def sync_folder(folder: str, first: str, last: str, dest: Path | None = None) -> list[Path]:
    """Download new or updated months; ENTSO-E regenerates past months without notice."""
    if not FOLDER.match(folder):
        raise ValueError(f"Invalid dataset folder name {folder!r}")
    if not (MONTH.match(first) and MONTH.match(last)) or last < first:
        raise ValueError("Expected months as YYYY-MM with first <= last")
    load_dotenv(config.ROOT / ".env")
    user = os.getenv("ENTSOE_USER", "").strip()
    password = os.getenv("ENTSOE_PASSWORD", "")
    if not user or not password:
        raise ValueError("Set ENTSOE_USER and ENTSOE_PASSWORD in the environment or .env")

    dest = dest or config.RAW_DIR / "entsoe_file_library" / folder
    dest.mkdir(parents=True, exist_ok=True)
    manifest_path = dest / MANIFEST
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    paths = []
    with requests.Session() as session:
        library = FileLibrary(session, user, password)
        remote = library.list_folder(folder)
        names = select_monthly(remote, first, last)
        if not names:
            raise ValueError(f"No monthly files in {folder} for {first}..{last}")
        for name in names:
            local = dest / name
            if not local.is_file() or manifest.get(name) != remote[name]:
                LOGGER.info("Downloading %s/%s", folder, name)
                rows = romanian_rows(library.download(folder, name), name)
                with tempfile.NamedTemporaryFile(dir=dest, suffix=".partial", delete=False) as f:
                    rows.to_csv(f, sep="\t", index=False)
                Path(f.name).replace(local)
                manifest[name] = remote[name]
                manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
            paths.append(local)
    return paths


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", required=True, help="Dataset folder under TP_export")
    parser.add_argument("--start", default=f"{config.TRAIN_START:%Y-%m}", help="First month YYYY-MM")
    parser.add_argument("--end", default=f"{config.TEST_END:%Y-%m}", help="Last month YYYY-MM")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        paths = sync_folder(args.folder, args.start, args.end)
    except (ValueError, OSError, requests.RequestException) as exc:
        # Request errors carry only the URL, never the POSTed credentials.
        parser.exit(1, f"File Library sync failed: {exc}\n")
    print(f"{len(paths)} files in {paths[0].parent}")


if __name__ == "__main__":
    main()
