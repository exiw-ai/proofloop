import hashlib
import re
from urllib.parse import urlparse


class SourceKeyGenerator:
    def generate_key(self, url: str, source_type: str, title: str | None = None) -> str:
        parsed = urlparse(url)

        if source_type == "arxiv":
            arxiv_match = re.search(r"(\d{4}\.\d{4,5})", url)
            if arxiv_match:
                return f"arxiv_{arxiv_match.group(1).replace('.', '_')}"

        if source_type == "github":
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 2:
                owner, repo = parts[0], parts[1]
                return f"github_{owner}_{repo}"[:30]

        if source_type == "semantic_scholar":
            paper_match = re.search(r"paper/([a-f0-9]+)", url)
            if paper_match:
                return f"s2_{paper_match.group(1)[:8]}"

        if title:
            slug = re.sub(r"[^a-zA-Z0-9]+", "_", title.lower())[:20]
            slug = slug.strip("_")
            if slug:
                return slug

        url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
        domain = parsed.netloc.replace("www.", "").split(".")[0]
        return f"{domain}_{url_hash}"

    def canonicalize_url(self, url: str) -> str:
        parsed = urlparse(url)

        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]

        path = parsed.path
        if path.endswith("/") and len(path) > 1:
            path = path[:-1]

        path = re.sub(r"//+", "/", path)

        canonical = f"{parsed.scheme}://{netloc}{path}"

        return canonical
