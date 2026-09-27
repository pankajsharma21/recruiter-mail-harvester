from pathlib import Path

from harvester.cli import load_config, make_setup
from harvester.profile import Profile

ROOT = Path(__file__).parent.parent


def example(name: str):
    """A Setup built from examples/profiles/<name>.toml and the shared config.toml."""
    profile = Profile.load(ROOT / "examples" / "profiles" / f"{name}.toml")
    return make_setup(load_config(ROOT / "config.toml"), name, profile)
