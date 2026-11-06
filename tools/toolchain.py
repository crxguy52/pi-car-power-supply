"""Toolchain paths and pins from config/toolchain.toml, merged with per-machine overrides.

Precedence, highest first: environment variables (ENV_OVERRIDES), config/toolchain.local.toml
(git-ignored), config/toolchain.toml. Works under the PDM python and KiCad's bundled python
(both 3.11, both have tomllib). Import it, or run it to print the merged config:

    python -I tools/toolchain.py            # all keys
    python -I tools/toolchain.py kicad_cli  # one resolved path (for shell scripts)
"""
import os
import pathlib
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = ROOT / 'config' / 'toolchain.toml'
LOCAL_CONFIG = ROOT / 'config' / 'toolchain.local.toml'

# environment variable -> (table, key)
ENV_OVERRIDES = {
    'PIPWR_KICAD_BIN_DIR': ('kicad', 'bin_dir'),
    'PIPWR_JAVA_EXE': ('java', 'exe'),
    'PIPWR_FREEROUTING_JAR': ('freerouting', 'jar'),
}

EXE_SUFFIX = '.exe' if os.name == 'nt' else ''


def _path(value):
    """Path with environment variables expanded (%LOCALAPPDATA% / $HOME), so the committed file is not per-user."""
    return pathlib.Path(os.path.expandvars(str(value)))


def _merge(base, extra):
    """Merge table-of-tables `extra` into `base` (key by key, so a local file may set one key only)."""
    for table, values in extra.items():
        base.setdefault(table, {}).update(values)
    return base


def load():
    """Merged config dict: committed file, then the local file, then environment variables."""
    with open(CONFIG, 'rb') as f:
        cfg = tomllib.load(f)
    if LOCAL_CONFIG.exists():
        with open(LOCAL_CONFIG, 'rb') as f:
            _merge(cfg, tomllib.load(f))
    for var, (table, key) in ENV_OVERRIDES.items():
        if os.environ.get(var):
            cfg.setdefault(table, {})[key] = os.environ[var]
    return cfg


class Toolchain:
    """Resolved paths and pins (attributes are pathlib.Path or str/int)."""

    def __init__(self, cfg=None):
        cfg = cfg or load()
        self.cfg = cfg
        self.kicad_bin = _path(cfg['kicad']['bin_dir'])
        self.kicad_version = str(cfg['kicad']['version'])
        self.kicad_cli = self.kicad_bin / f'kicad-cli{EXE_SUFFIX}'
        self.kicad_python = self.kicad_bin / f'python{EXE_SUFFIX}'
        self.java = _path(cfg['java']['exe'])
        self.java_min_major = int(cfg['java']['min_major'])
        self.freerouting_jar = _path(cfg['freerouting']['jar'])
        self.freerouting_version = str(cfg['freerouting']['version'])
        self.freerouting_sha256 = str(cfg['freerouting']['sha256']).lower()

    def as_dict(self):
        return {k: v for k, v in vars(self).items() if k != 'cfg'}


def main(argv):
    tc = Toolchain()
    items = tc.as_dict()
    if len(argv) > 1:
        print(items[argv[1]])
    else:
        for k, v in items.items():
            print(f'{k} = {v}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
