"""Convert directories, files, and ZIP files to WARC web archives."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("warcit")
except PackageNotFoundError:
    __version__ = "unknown"
