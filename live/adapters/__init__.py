import os


def get_adapter(name=None):
    """Pick the price source from LIVE_SOURCE in .env (default: fake)."""
    name = (name or os.environ.get("LIVE_SOURCE", "fake")).strip().lower()
    if name == "fake":
        from .fake import FakeAdapter
        return FakeAdapter()
    if name == "template":
        from .template import TemplateAdapter
        return TemplateAdapter()
    # add your own here:  if name == "mysource": ...
    raise ValueError(f"Unknown LIVE_SOURCE '{name}'. Known sources: fake, template")
