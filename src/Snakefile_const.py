import glob
import os
import pathlib

import pandas as pd

pwd = pathlib.Path(os.getcwd())
proj_dir = pwd.parents[0]

DATA = proj_dir / "data"
RAW = DATA / "raw"
END = DATA / "processed"
INT = DATA / "interim"

DATAs = str(DATA) + "/"
RAWs = str(RAW) + "/"
INTs = str(INT) + "/"

CONFIG = proj_dir / "configs"
CONFIGs = str(CONFIG) + "/"

LOG = INT / "logs"
REQ = proj_dir / "reqs"
SRC = proj_dir / "src"
DOCS = proj_dir / "docs"
