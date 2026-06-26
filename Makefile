.PHONY: all data zones panel analyze figures test clean reproduce
PY := python
SRC := src

all: reproduce

# Full pipeline from scratch (downloads ~1.8 GB of raw parquet on first run).
reproduce: data zones panel analyze figures

data:            ## download TLC parquet for the study window (auto-latest month)
	$(PY) $(SRC)/download.py

zones:           ## derive the Congestion Relief Zone from the cbd_congestion_fee field
	$(PY) $(SRC)/zones.py

panel:           ## build daily DiD panels from the parquet
	$(PY) $(SRC)/build_panel.py

analyze:         ## run DiD, event study, parallel-trends, robustness
	$(PY) $(SRC)/did.py
	$(PY) $(SRC)/robustness.py

figures:         ## render figures + Tableau export CSVs
	$(PY) $(SRC)/viz.py

test:
	$(PY) -m pytest -q

clean:
	rm -rf results figures/*.png data/panel_*.csv data/tableau_*.csv

# The committed panels let you reproduce the analysis without the raw download:
#   pip install -r requirements.txt && make analyze figures
