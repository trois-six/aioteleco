"""MkDocs hooks for the documentation site (``mkdocs.yml``).

``docs/protocol/`` is an OKF bundle holding both ``index.md`` (the bundle index) and
``README.md`` (the overview note). MkDocs maps both to ``protocol/index.html`` and would
drop ``README.md`` with a warning; ``mkdocs.yml`` excludes it from the scan and this hook
publishes it at ``protocol/overview/`` instead, so the bundle files stay untouched.
"""

from __future__ import annotations

from typing import Any

from mkdocs.structure.files import File, Files, InclusionLevel

OVERVIEW_SRC = "protocol/README.md"


def on_files(files: Files, config: Any) -> Files:
    """Publish the protocol overview note under its own URL."""
    existing = files.get_file_from_path(OVERVIEW_SRC)
    if existing is not None:
        files.remove(existing)
    dest = "protocol/overview/index.html" if config.use_directory_urls else "protocol/overview.html"
    files.append(
        File(
            OVERVIEW_SRC,
            config.docs_dir,
            config.site_dir,
            config.use_directory_urls,
            dest_uri=dest,
            inclusion=InclusionLevel.INCLUDED,
        )
    )
    return files
