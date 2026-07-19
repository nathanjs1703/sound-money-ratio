# Sound Money Ratio: command-line tool

The command-line application to the Sound Money Ratio project. See the [project README](../README.md) for the thesis and the other applications.

## Quickstart

```bash
git clone https://github.com/nathanjs1703/sound-money-ratio.git
cd sound-money-ratio
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python3 cli/project.py --base gold 180
```

```
Holding bitcoin for 180 days was profitable in gold in XX.X% of historical windows.

Chart saved to btc-gold-chart.html
```

The chart opens in your browser automatically and is saved to the directory from which the tool was run.

**Arguments.** `--base` is the asset you start and end in (`gold` or `bitcoin`); the positional argument is the holding period in days. Both are optional. The tool defaults to gold and 180 days, and tells you when it does.

```bash
python3 cli/project.py                      # gold base, 180 days
python3 cli/project.py --base bitcoin 90    # bitcoin base, 90 days
```

**First run** downloads price history from Yahoo Finance into a `cache/` folder (you'll see yfinance's progress bars). Subsequent runs reuse the cache until it goes stale.

**Tests:** `pytest` from the project root.

## Reading the chart

The chart plots the full ratio history — from the earliest date bitcoin price data exists (around 2014) to the most recent data available, minus the holding period at the tail, since those dates have no exit yet.

Each point on the line is an entry date. The area beneath it is **green** if a window opening on that date closed profitably, and **red** if it did not. The Historical Success Rate is simply the green share.

With a **gold base**, the chart shows the BTC/Gold ratio in oz of gold per BTC, and historically has been trending up. With a **bitcoin base**, it shows the Gold/BTC ratio in BTC per oz of gold, and historically has been trending down. These are the reciprocal histories with reciprocal charts, not the same chart flipped.  However, the two success rates are exact complements: a window profitable in one base is unprofitable in the other, so the rates sum to 1. (A window that ended exactly where it began would belong to neither. However, at daily float precision that never occurs.)

The success rate is a historical frequency, not an infallible forecast. See [Known limitations](#known-limitations).

## Design decisions

**Base asset neutrality.** The original version hardcoded a hidden premise: _gold is home_. You started in gold, bought bitcoin, sold back to gold, and "profitable" meant ending with more gold. The bias was mostly in the _direction of the question_, not the code. The tool hid the mirror question: was holding gold good for a bitcoin-owner?

Rather than compute the original BTC/Gold and then invert it for the bitcoin case, the chosen base selects the numerator and denominator at construction inside `align_and_compute_ratio`, either `price_btc / price_gold` or `price_gold / price_btc`, both built directly from each dollar-denominated price series. Neither ratio is canonical; neither is derived from the other. A direct division also avoids the float error a reciprocal round-trip can introduce, which matters here because the tests assert exact ratio values in both frames.

`base` enters the analysis functions as a plain string (`"gold"` or `"bitcoin"`), exactly as `holding_period_days` enters as a plain int. `main` translates the CLI argument into that value; the analysis layer never touches `argparse`. The CLI is therefore a thin caller operating on a shared core. So a future interactive slider will drive the same neutral core without any change to the analysis code.

There is enough presentation needed around these two assets that it justified a bit of code, namely a dictionary, to manage it. `BASE_PRESENTATION` is a module-level dict holding the facts of each frame, like numerator, denominator, unit label. Each surface composes its own phrasing from those facts, so the chart title, the axis label, and the terminal output cannot disagree about what frame they are in.

**Forward-fill for gaps.** Gold doesn't trade on weekends; bitcoin does. On top of that, the data provider occasionally drops a day. Both problems are solved the same way, in two stages: reindex to a continuous daily range (which exposes every gap as an explicit empty row), then forward-fill.

Forward-fill specifically is used, not interpolation, not backfill. Both of those would use a future price to fill a past gap, which means the window analysis would be reading prices that did not exist yet on the day it claims to be trading. Propagating the last known price is the conservative choice: it can be stale, but it is never clairvoyant.

The continuous daily index is also a deliberate model of what a holding period *is*. "Hold for 90 days" means 90 wall-clock days, not 90 trading days, and the dense index is the honest representation of that.

Finally, `dropna(subset=["price_btc"])` trims the leading gold-only history. Yahoo Finance has gold back to 2000 and bitcoin only to 2014; there's no ratio to compute before both exist.

**Vectorized windows.** The first version of `compute_windows` looped over `iterrows()`, looking up each exit by date. That was hedging for correctness through a familiar technique and a deliberate choice while learning pandas. It's also the wrong shape for what comes next: an interactive slider recomputes every window on every drag, so the loop becomes visible lag.

The vectorized form is a single row-shift, `ratio_df["ratio"].shift(-N)`, which aligns each entry with its exit for a per-element comparison. **This is only equivalent to the loop's date-based lookup because the index is dense**. It has one row per calendar day, guaranteed upstream by the reindex + ffill above. That cross-function coupling is the assumption the whole vectorization rests on, and it's noted in the docstring for the next person who touches it.

The refactor was done with a characterization-test first: the loop's exact output was captured as ground truth across several holding periods (including ties and boundary values), and the vectorized version had to reproduce it identically before I removed the loop.

**Segment-based chart coloring.** The commonly known way to get a two-color fill in Plotly is the "NaN trick": two traces, one green and one red, each holding `NaN` wherever the other color applies. It doesn't work with `fill="tozeroy"` and that is a known Plotly.js rendering bug, and the result was the entire area filled brown.

The working approach detects same-color runs with `(profitable != profitable.shift()).cumsum()`, splits the frame on those runs, and adds one filled trace per run. This lives in `generate_chart` rather than being extracted into the analysis layer, because segmenting a series for the renderer's benefit is a rendering concern. It has no analytical meaning.

**Holding-period guard.** `compute_windows` rejects a holding period of `len(ratio_df) - 1` or greater. That is one day shorter than the arithmetic actually requires for plotly to successfully execute a chart. That looks like an off-by-one. It isn't; it's a UX decision, settled by hand-tracing the output rather than by argument. A holding period one day below the arithmetic limit yields a single surviving window, and a chart of a single point has nothing to show: no change in ratio, no fill, no color. Two points is the minimum that renders as a chart with meaningful information, so two points is the floor the guard enforces.

**Caching and freshness.** Price data is cached to CSV, and re-fetched only when the cache is older than `CACHE_MAX_AGE_IN_DAYS`. Yahoo Finance adds one price per day per asset, so hitting the API on every run buys nothing — a cache that's a few days stale gives the same answer to essentially every question this tool is asked. During development the same cache is what makes it possible to iterate without hammering someone else's free service.

**Why yfinance.** It covers both bitcoin and gold with enough history, and it's free. A paid data source would have made the tool marginally better and dramatically less likely to be run by anyone who isn't me.

## Known limitations

### Core

- **History starts in 2014.** Yahoo Finance's bitcoin coverage doesn't go back further, though bitcoin does. How much the missing early years are worth is debatable since bitcoin was in an adoption phase and gold was not, but the gap is real.
- **Forward-fill is lossy.** Weekend and gap prices are propagated, not observed. Any conclusion drawn at day-to-day resolution should be treated with suspicion, while at the same time that sort of trading analysis is not what this tool was designed for. 
- **The ratio is synthetic.** It's constructed by dividing two USD-mediated series. Small markets exist trading bitcoin against tokenized gold, but there is no appreciably large native market where bitcoin trades directly against physical spot gold. The ratio is a derived quantity, not an observed price.
- **Supply adjustment was measured and deliberately not implemented.** Bitcoin and gold both dilute, at different rates, so a constant-supply framing would tilt the ratio slightly. That tilt was measured against the real price history across holding periods and both bases before deciding: the largest movement in the success rate anywhere was 1.1 percentage points, well inside the tool's existing noise. Because gold dilutes faster than bitcoin, the correction runs in one direction, meaning the raw ratio very slightly understates bitcoin's performance on a scarce-versus-scarce basis at long holds. The feature was dropped rather than built because the effect does not meaningfully change any answer the tool gives.
- **The success rate is a frequency, not a probability.** It describes what happened, and is only a useful guide to what will happen insofar as the future resembles the past. That's the tool's entire premise and also its central caveat. _This is not financial advice._

### Command-line specifics

- **A yfinance outage crashes the tool.** Currently the traceback is the error message. Acceptable for a CLI audience; not acceptable once there's a browser in front of it, and it's on the roadmap to fix before then.

## Project layout

The analysis lives in a shared core at the repo root; the CLI is a thin caller on top of it.

```
sound-money-ratio/
├── sound_money_core.py   pure analysis, no caller-specific imports
├── test_core.py          tests for the core
├── conftest.py           makes both modules importable in tests
└── cli/
    ├── project.py        data fetching, chart rendering, CLI entry point
    └── test_cli.py       tests for the CLI
```

The pipeline runs **data → analysis → visualization**, with `main` orchestrating from above rather than participating:

| Stage | Location | Functions |
|---|---|---|
| **data** | `cli/project.py` | `fetch_price_data` |
| **analysis** | `sound_money_core.py` | `align_and_compute_ratio` · `compute_windows` · `calculate_success_rate` · `amend_ratio_with_profitability` |
| **visualization** | `cli/project.py` | `generate_chart` |

The analysis functions are pure, which is why they're the ones under test and why they're the ones that live in the shared core. `fetch_price_data` (network + filesystem) and `generate_chart` (writes a file) are side-effect machines and are covered only at their error boundaries. Run the suite with `pytest` from the project root.

## Roadmap

- **Interactive holding-period slider** — drag the period, watch the chart and success rate recompute live. The vectorization above is what makes this feasible.
- **Web deployment** — the next goal. A tool that requires you to clone a repo and stand up a virtualenv is a tool for people who already know how to do that, which is great if that's you. However, further development will open the tool up to a much wider audience. 
- **CI** — run the test suite on push. (Also: earns an honest build badge, which the ones above currently are not a substitute for.)
