"""`python -m nxceviri.arac <komut>`: `python -m nxceviri <komut>` ile aynı araçlar."""

import sys

from nxceviri.arac import main

sys.exit(main(sys.argv[1:]))
