"""GitHub client using gh CLI via subprocess."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GitHubClient:
    """Interact with GitHub through the `gh` CLI.

    Requires ``gh`` to be installed and authenticated (``gh auth login``).
    """

    owner: str = ""
    repo: str = ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a gh CLI command and return the completed process."""
        cmd = ["gh", *args]
        logger.debug("Running: %s", " ".join(cmd))
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if check and result.returncode != 0:
            msg = f"gh command failed ({result.returncode}): {result.stderr.strip()}"
            logger.error(msg)
            raise RuntimeError(msg)
        return result

    @staticmethod
    def _parse_json(text: str) -> Any:
        """Best-effort JSON parse of gh output."""
        text = text.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}

    # ------------------------------------------------------------------
    # Repository management
    # ------------------------------------------------------------------

    def create_repo(
        self,
        name: str,
        *,
        description: str = "",
        private: bool = False,
        auto_init: bool = True,
    ) -> dict[str, Any]:
        """Create a new GitHub repository.

        Returns the parsed JSON response from gh.
        """
        args = ["repo", "create", name, "--json", "name,url,databaseId"]
        if description:
            args.extend(["--description", description])
        if private:
            args.append("--private")
        else:
            args.append("--public")
        if auto_init:
            args.append("--clone")
        result = self._run(args)
        return self._parse_json(result.stdout)

    # ------------------------------------------------------------------
    # README management
    # ------------------------------------------------------------------

    def update_readme(self, content: str, *, message: str = "Update README") -> dict[str, Any]:
        """Update README.md via the gh API (REST wrapper).

        Uses ``gh api`` to create or update the file.
        """
        import base64

        target = f"{self.owner}/{self.repo}" if self.owner and self.repo else self.repo
        if not target:
            raise ValueError("owner and repo must be set before calling update_readme()")

        # Try to get existing SHA first
        get_args = ["api", f"repos/{target}/contents/README.md", "--jq", ".sha"]
        sha_result = self._run(get_args, check=False)
        sha = sha_result.stdout.strip() if sha_result.returncode == 0 else None

        encoded = base64.b64encode(content.encode()).decode()
        payload: dict[str, Any] = {
            "message": message,
            "content": encoded,
        }
        if sha:
            payload["sha"] = sha

        args = [
            "api",
            f"repos/{target}/contents/README.md",
            "--method",
            "PUT",
            "-f",
            f"message={message}",
            "-f",
            f"content={encoded}",
        ]
        if sha:
            args.extend(["-f", f"sha={sha}"])

        result = self._run(args)
        return self._parse_json(result.stdout)

    # ------------------------------------------------------------------
    # Topics / tags
    # ------------------------------------------------------------------

    def add_topics(self, topics: list[str]) -> dict[str, Any]:
        """Replace repository topics via gh CLI."""
        target = f"{self.owner}/{self.repo}"
        if not target.replace("/", ""):
            raise ValueError("owner and repo must be set before calling add_topics()")

        args = [
            "repo",
            "edit",
            target,
            "--add-topic",
            ",".join(topics),
        ]
        result = self._run(args, check=False)
        if result.returncode != 0:
            logger.warning("add_topics returned non-zero: %s", result.stderr.strip())
        return {"topics": topics, "ok": result.returncode == 0}

    # ------------------------------------------------------------------
    # Analytics (release / issue counts via API)
    # ------------------------------------------------------------------

    def get_analytics(self) -> dict[str, Any]:
        """Fetch lightweight repo analytics via gh api."""
        target = f"{self.owner}/{self.repo}"
        result = self._run(
            ["api", f"repos/{target}", "--jq",
             '{"stars": .stargazers_count, "forks": .forks_count, '
             '"open_issues": .open_issues_count, "watchers": .subscribers_count}'],
            check=False,
        )
        if result.returncode != 0:
            logger.warning("get_analytics failed: %s", result.stderr.strip())
            return {}
        return self._parse_json(result.stdout)

    # ------------------------------------------------------------------
    # Post creation (release)
    # ------------------------------------------------------------------

    def create_post(
        self,
        title: str,
        body: str,
        *,
        tag_name: str | None = None,
        draft: bool = False,
    ) -> dict[str, Any]:
        """Create a GitHub Release (used as a 'post' on GitHub).

        If *tag_name* is ``None`` a simple slug from *title* is used.
        """
        target = f"{self.owner}/{self.repo}"
        tag = tag_name or title.lower().replace(" ", "-")[:60]

        args = [
            "release",
            "create",
            tag,
            "--repo",
            target,
            "--title",
            title,
            "--notes",
            body,
        ]
        if draft:
            args.append("--draft")
        result = self._run(args, check=False)
        if result.returncode != 0:
            logger.error("create_post failed: %s", result.stderr.strip())
            return {"ok": False, "error": result.stderr.strip()}
        return {"ok": True, "tag": tag, "output": result.stdout.strip()}
