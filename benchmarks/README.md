# Benchmarks (FR-PM-09)

Reproducible numbers for the predictive-maintenance models on public datasets, compared with the
PRD §4.5 targets. The code is `packages/pdm/src/twinvoice_pdm/benchmark/`. The API's
`POST /api/v1/benchmarks/run` (the Benchmarks page at `/models/benchmarks`) and this CLI both run it,
so a number in the UI and a number here mean the same thing.

## Data

```sh
python data/download.py cmapss ai4i metropt3   # sha256-verified, into data/raw/<name>/
```

## Run

In the worker container (it has `data/raw` mounted and writes a `benchmark_runs` row):

```sh
make benchmark                      # all six datasets, about 3 minutes
make benchmark DATASETS=FD001,AI4I
make benchmark-quick                # subsampled smoke run, seconds; not comparable to published numbers
```

From a host shell, using the pdm environment:

```sh
cd packages/pdm
uv run python ../../benchmarks/run.py --datasets FD001,AI4I --seed 42 [--quick]
```

This writes `benchmarks/results/<YYYY-MM-DD>.md`. It also records a `benchmark_runs` row when
`TV_DATABASE_URL` is set (the pdm environment has no psycopg, so do that from the worker).

## Protocols

| Dataset | Model | Split | Metrics |
|---|---|---|---|
| C-MAPSS FD001–FD004 | LightGBM on 30-cycle windows (mean, std, slope, last, min, max per informative sensor, plus the cycle count). FD002 and FD004 use KMeans(6) operating-condition z-scoring fitted on train. MAPIE CV+ 90 % intervals with engine-grouped folds. | Official train/test split. Each test engine is scored on its last window against `RUL_FD00x.txt`. RUL is capped at 125. | `rmse`, `nasa_score`, `coverage_90`, `interval_width` |
| AI4I 2020 | LightGBM with balanced class weights, isotonic calibration inside each fold. The TWF/HDF/PWF/OSF/RNF leakage columns are dropped. | Stratified 5-fold, scored out of fold. | `auc`, `f1` (at the best out-of-fold threshold, which is reported too), `ece` |
| MetroPT-3 | IsolationForest on 60-minute windows of the analogue sensors, fitted on the healthy period ending 7 days before the first reported failure. | The four failure reports in `Data Description_Metro.pdf`, with a 48 h detection horizon. | `event_recall`, `event_precision`, `mean_lead_time_h` |

The seed is fixed (`--seed`, default 42). Each report records the git commit (`TV_GIT_SHA` inside
containers) and the dataset archive sha256 values from `data/raw/<name>/.complete`.

The MetroPT-3 alarm threshold was chosen by a small sweep scored on the same four failures. No
other labelled period exists to tune on, so its recall and precision are optimistic.
