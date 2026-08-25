# signaldeck_sdk/context.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Optional, Any
import datetime

class FileService(Protocol):
    def save(self, file: Any, path: str) -> str:
        """Persist an uploaded file to `path` and return the final path."""
        ...

class Renderer(Protocol):
    def render(self, template: str, **kwargs) -> str:
        """Render a template with kwargs and return HTML."""
        ...

class UrlResolver(Protocol):
    def forFile(self, pluginName: str, filePath: str) -> str:
        """Return a URL for a file given its plugin name and path."""
        ...

class Translator(Protocol):
    def t(self, key: str, **kwargs) -> str:
        """Translate a key with optional formatting kwargs."""
        ...
    
    def load_from_packages(self, packages: list[str]) -> None:
        """Load/merge translations from a list of packages."""
        ...

class DateProvider:
    def now(self, tz= None):
        return datetime.datetime.now(tz = tz)

@dataclass(frozen=True)
class ApplicationContext:
    """
    SDK-level context: only contracts/types, no Flask imports.
    Concrete implementation is provided by signaldeck-core.
    """
    renderer: Renderer
    url: UrlResolver
    files: FileService
    translator: Translator
    values: Any  # can be typed to ValueProvider later
    logger: Any  # can be typed later (logging.Logger)
    date: DateProvider = DateProvider()

    def render(self, template: str, **kwargs) -> str:
        return self.renderer.render(template, **kwargs)
    
    def t(self, key: str, **kwargs) -> str:
        return self.translator.t(key, **kwargs)

