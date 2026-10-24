"""Scanner adapter factory — resolves the configured ScannerAdapter set
based on settings.SCANNER_MODE.

In MOCK mode, a single MockScanner instance is used for all three "tools"
so the Assessment Agent's aggregation logic (which calls each adapter and
merges results) is exercised identically in both modes without special-
casing mock mode as "just return one list."
"""
from app.config import ScannerMode, settings
from app.scanners.base import ScannerAdapter
from app.scanners.mock_scanner import MockScanner
from app.scanners.nmap_adapter import NmapAdapter
from app.scanners.nuclei_adapter import NucleiAdapter
from app.scanners.zap_adapter import ZapAdapter


def get_scanner_adapters() -> list[ScannerAdapter]:
    """Returns the list of ScannerAdapter instances the Assessment Agent
    should invoke, one per configured tool."""
    if settings.SCANNER_MODE == ScannerMode.MOCK:
        return [MockScanner()]
    return [NucleiAdapter(), ZapAdapter(), NmapAdapter()]