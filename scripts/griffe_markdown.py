"""Griffe extension for the documentation site (``mkdocs.yml``).

The docstrings are plain reST-flavoured text, but mkdocstrings renders them as Markdown:

* a bare ``>>>`` doctest block would become nested blockquotes, so it is wrapped in a
  ``pycon`` code fence;
* Sphinx roles such as ``:class:`TelecoHub``` are turned into inline code.
"""

from __future__ import annotations

import re
from typing import Any

import griffe

PROMPTS = (">>>", "...")
SPHINX_ROLE = re.compile(r":(?:py:)?(?:class|func|meth|attr|mod|data|exc|obj):`~?([^`]+)`")


def fence_doctests(text: str) -> str:
    """Wrap runs of ``>>>`` / ``...`` lines in a fenced ``pycon`` block."""
    out: list[str] = []
    in_block = False
    for line in text.splitlines():
        is_prompt = line.lstrip().startswith(PROMPTS)
        if is_prompt and not in_block:
            if out and out[-1].strip():
                out.append("")
            out.append("```pycon")
            in_block = True
        elif not is_prompt and in_block:
            out.append("```")
            in_block = False
        out.append(line)
    if in_block:
        out.append("```")
    return "\n".join(out)


def to_markdown(text: str) -> str:
    """Make a reST-flavoured docstring render well as Markdown."""
    text = SPHINX_ROLE.sub(r"`\1`", text)
    if ">>>" in text:
        text = fence_doctests(text)
    return text


class MarkdownDocstrings(griffe.Extension):
    """Apply ``to_markdown`` to every docstring."""

    def on_object(self, *, obj: griffe.Object, **kwargs: Any) -> None:
        if obj.docstring is not None:
            obj.docstring.value = to_markdown(obj.docstring.value)
