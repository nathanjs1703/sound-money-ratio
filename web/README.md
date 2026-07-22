# Sound Money Ratio — web application

The web application for the Sound Money Ratio project. See the [project README](../README.md) for the thesis and the other applications.

**Live at [nathanjs1703.github.io/sound-money-ratio](https://nathanjs1703.github.io/sound-money-ratio/).**

| Short holds | Long holds |
|:---:|:---:|
| ![BTC/Gold ratio, 30-day hold — green and red windows in roughly even stripes](../assets/chart-30d.png) | ![BTC/Gold ratio, 752-day hold — mostly green with occasional red bands](../assets/chart-752d.png) |
| Gold base, 30-day hold · as of 2026-07-14 · near even | Gold base, 752-day hold · as of 2026-07-14 · 75.2% of windows profitable |

## How it works

Enter a holding period in days, select a base asset (gold or bitcoin), and hit Analyze. The tool returns a chart and a plain-language sentence telling you how often that trade was profitable across the full shared history of bitcoin and gold.

The tool accepts any integer holding period from 1 to the length of the available price history. Both base assets are available. The chart and sentence update on each analysis.

## Reading the chart

The chart plots the full ratio history — from the earliest date bitcoin price data exists (around 2014) to the most recent data available, minus the holding period at the tail, since those dates have no exit yet.

Each point on the line is an entry date. The area beneath it is **green** if a window opening on that date closed profitably, and **red** if it did not. The Historical Success Rate is simply the green share.

With a **gold base**, the chart shows the BTC/Gold ratio in oz of gold per BTC, and historically has been trending up. With a **bitcoin base**, it shows the Gold/BTC ratio in BTC per oz of gold, and historically has been trending down. These are the reciprocal histories with reciprocal charts, not the same chart flipped. However, the two success rates are exact complements: a window profitable in one base is unprofitable in the other, so the rates sum to 1. (A window that ended exactly where it began would count as profitable in neither base, and forward-fill makes such ties structurally possible: a day where both series are gap-filled repeats the previous ratio bit-for-bit. Checked empirically, it doesn't happen: across every holding period tested there is not a single exact tie in this data, because bitcoin trades every calendar day and a simultaneous gap in both series would be very rare. So the complement is exact here, not merely approximate.)

The success rate is a historical frequency, not an infallible forecast. See [Known limitations](#known-limitations).

## Design decisions

### Core

**Monorepo split.** This project has one analytical core and two applications (a CLI and a web app) that present the same analysis to different audiences. They live in a single repository rather than being split into separate packages, because the shared core is a single Python module and the overhead of packaging it would add complexity without solving a problem the project actually has. Each application is a thin caller: neither modifies the core's behavior, and both produce identical analytical results. The directory structure follows from this: the core sits at the repo root, each application has its own subdirectory (`cli/`, `web/`), and each carries its own README documenting application-specific concerns. Design decisions and known limitations that belong to the core are duplicated in both application READMEs so that each stands alone without cross-references.

**Base asset neutrality.** The original version hardcoded a hidden premise: _gold is home_. You started in gold, bought bitcoin, sold back to gold, and "profitable" meant ending with more gold. The bias was mostly in the _direction of the question_, not the code. The tool hid the mirror question: was holding gold good for a bitcoin-owner?

Rather than compute the original BTC/Gold and then invert it for the bitcoin case, the chosen base selects the numerator and denominator at construction inside `align_and_compute_ratio`, either `price_btc / price_gold` or `price_gold / price_btc`, both built directly from each dollar-denominated price series. Neither ratio is canonical; neither is derived from the other. A direct division also avoids the float error a reciprocal round-trip can introduce, which matters here because the tests assert exact ratio values in both frames.

`base` enters the analysis functions as a plain string (`"gold"` or `"bitcoin"`), exactly as `holding_period_days` enters as a plain int. Each application translates its own input into that value; the analysis layer never touches CLI argument parsing or browser rendering. Each application is therefore a thin caller operating on the shared core, importing it with no modification.

There is enough presentation needed around these two assets that it justified a bit of code, namely a dictionary, to manage it. `BASE_PRESENTATION` is a module-level dict holding the facts of each frame, like numerator, denominator, unit label. Each surface composes its own phrasing from those facts, so the chart title, the axis label, and the terminal output cannot disagree about what frame they are in.

**Forward-fill for gaps.** Gold doesn't trade on weekends; bitcoin does. On top of that, the data provider occasionally drops a day. Both problems are solved the same way, in two stages: reindex to a continuous daily range (which exposes every gap as an explicit empty row), then forward-fill.

Forward-fill specifically is used, not interpolation, not backfill. Both of those would use a future price to fill a past gap, which means the window analysis would be reading prices that did not exist yet on the day it claims to be trading. Propagating the last known price is the conservative choice: it can be stale, but it is never clairvoyant.

The continuous daily index is also a deliberate model of what a holding period *is*. "Hold for 90 days" means 90 wall-clock days, not 90 trading days, and the dense index is the honest representation of that.

Finally, `dropna(subset=["price_btc"])` trims the leading gold-only history. Yahoo Finance has gold back to 2000 and bitcoin only to 2014; there's no ratio to compute before both exist.

**Vectorized windows.** The first version of `compute_windows` looped over `iterrows()`, looking up each exit by date. That hedged for correctness through a familiar technique, a deliberate choice while learning pandas. It's also the wrong shape for interactive use; any caller that recomputes on every input change would see the loop as visible lag.

The vectorized form is a single row-shift, `ratio_df["ratio"].shift(-N)`, which aligns each entry with its exit for a per-element comparison. **This is only equivalent to the loop's date-based lookup because the index is dense**. It has one row per calendar day, guaranteed upstream by the reindex + ffill above. That cross-function coupling is the assumption the whole vectorization rests on, and it's noted in the docstring for the next person who touches it.

The refactor was done with a characterization-test first: the loop's exact output was captured as ground truth across several holding periods (including ties and boundary values), and the vectorized version had to reproduce it identically before I removed the loop.

**Segment-based chart coloring.** The commonly known way to get a two-color fill in Plotly is the "NaN trick": two traces, one green and one red, each holding `NaN` wherever the other color applies. It doesn't work with `fill="tozeroy"` and that is a known Plotly.js rendering bug, and the result was the entire area filled brown.

The working approach detects same-color runs with `(profitable != profitable.shift()).cumsum()`, splits the frame on those runs, and adds one filled trace per run. This lives in the rendering layer rather than being extracted into the analysis core, because segmenting a series for the renderer's benefit is a rendering concern. It has no analytical meaning.

**Holding-period guard.** `compute_windows` rejects a holding period of `len(ratio_df) - 1` or greater. That looks like an off-by-one. It isn't. Yes, a period of `len(ratio_df) - 1` still yields a single surviving window, and Plotly renders it without complaint: one point, no line, no fill, no color, a chart that shows nothing. However, two points is the minimum that renders as a chart with meaningful information, so two points is the floor the guard enforces. This is a UX decision, settled by hand-tracing the output rather than by argument alone.

**Why yfinance.** It covers both bitcoin and gold with enough history, and it's free. A paid data source would have made the tool marginally better and dramatically less likely to be run by anyone who isn't me.

### Web app

**Static deploy and the publish-time boundary.** The web app is a static site hosted on GitHub Pages. There is no backend server: no process listening for requests, no cold starts, no hosting bill, nothing to maintain or keep alive. This is a deliberate choice driven by the project's primary UX goal: a URL that works instantly for anyone, anytime.

The architecture has two halves: a publish pipeline that runs in CI, and a browser-side analytical core that runs on the visitor's machine. The boundary between them sits at alignment. A GitHub Action runs daily, fetches fresh prices via yfinance, runs the shared Python core's alignment logic (`align_and_compute_ratio` from `sound_money_core.py`, imported directly with no modification), and writes a `data.json` file containing the dense, forward-filled daily price series. All the epistemically loaded work — the outer join, the reindex to a continuous daily range, the forward-fill, the leading-NaN trim — stays in Python, runs once at publish time, and ships as already-clean data. The result is deployed to GitHub Pages as a static file alongside the page.

When a visitor submits a holding period and base, four JavaScript functions in `core.js` compute the ratio, classify windows, calculate the success rate, and detect chart segments. They mirror only the downstream arithmetic from `sound_money_core.py`. The chart is rendered by Plotly.js, the same engine the CLI's HTML output uses.

**JS mirror and parity testing.** The browser-side compute means four analytical functions exist in both Python and JavaScript. This is a real duplication cost, accepted because the alternative (a backend server) directly conflicts with the zero-friction static hosting goal. The defense is cross-language characterization testing: the publish pipeline emits a `fixtures.json` file containing Python-computed success rates at a spread of holding periods and both bases, and `test_parity.js` runs in CI before every deploy, asserting that the JS functions reproduce them exactly. If the mirror ever drifts from the Python core, the deploy fails and the site does not update. The parity gate covers the three analytical functions: ratio, windows, success rate. `computeSegments` sits outside it for the same reason segmenting stays out of the Python core: it is a rendering concern with no analytical meaning to assert against.

## Known limitations

### Core

- **History starts in 2014.** Yahoo Finance's bitcoin coverage doesn't go back further, though bitcoin does. How much the missing early years are worth is debatable since bitcoin was in an adoption phase and gold was not, but the gap is real.
- **Forward-fill is lossy.** Weekend and gap prices are propagated, not observed. Any conclusion drawn at day-to-day resolution should be treated with suspicion, while at the same time that sort of trading analysis is not what this tool was designed for.
- **The ratio is synthetic.** It's constructed by dividing two USD-mediated series. Small markets exist trading bitcoin against tokenized gold, but there is no appreciably large native market where bitcoin trades directly against physical spot gold. The ratio is a derived quantity, not an observed price.
- **Supply adjustment was measured and deliberately not implemented.** Bitcoin and gold both dilute, at different rates, so a constant-supply framing would tilt the ratio slightly. That tilt was measured against the real price history across holding periods and both bases before deciding: the largest movement in the success rate anywhere was 1.1 percentage points, well inside the tool's existing noise. Because gold dilutes faster than bitcoin, the correction runs in one direction, meaning the raw ratio very slightly understates bitcoin's performance on a scarce-versus-scarce basis at long holds. The feature was dropped rather than built because the effect does not meaningfully change any answer the tool gives.
- **The success rate is a frequency, not a probability.** It describes what happened, and is only a useful guide to what will happen insofar as the future resembles the past. That's the tool's entire premise and also its central caveat. _This is not financial advice._

### Web app

- **Data freshness is daily, not live.** The GitHub Action runs once per day. A visitor sees whatever the most recent run produced, not a live fetch. For a historical-frequency tool this is more than adequate, but the price history will always be at most one day behind.
- **The JS mirror is a maintenance obligation.** Any future change to the Python core's arithmetic or presentation labels must be made in `core.js` as well. The parity test catches drift but does not eliminate the double work.
- **No offline support.** The page fetches `data.json` on every load. If GitHub Pages is unreachable, the page shows a loading error.
- **Mirror drift introduced by a push is caught at the next deploy, not at push time.** The parity test needs fresh fixtures, which means a live yfinance fetch; running it on every push would make the test suite flaky and lean harder on a free API. The daily deploy is the gate: if a change breaks parity, the next deploy fails and the live site keeps serving the last good build.

## Project layout

The analysis lives in a shared core at the repo root; the CLI and web app are thin callers on top of it.

```
sound-money-ratio/
├── sound_money_core.py   pure analysis, no caller-specific imports
├── test_core.py          tests for the core
├── conftest.py           makes both modules importable in tests
├── cli/
│   ├── project.py        data fetching, chart rendering, CLI entry point
│   ├── test_cli.py       tests for the CLI
│   └── README.md         CLI usage and design decisions
└── web/
    ├── index.html        page: controls, chart, sentence, explanatory text
    ├── core.js           JS analytical mirror (four functions)
    ├── publish.py        CI: generates data.json and fixtures.json
    ├── test_parity.js    CI: deploy-gate parity test
    └── README.md         this file
```

`data.json` and `fixtures.json` are generated artifacts, not committed. The GitHub Action creates them fresh each run.

The web app pipeline:

| Stage | Where it runs | What it does |
|---|---|---|
| **fetch + align** | CI (`publish.py`) | yfinance download, `align_and_compute_ratio`, write `data.json` |
| **parity gate** | CI (`test_parity.js`) | assert JS core matches Python-computed fixtures |
| **compute + render** | browser (`core.js` + `index.html`) | ratio, windows, success rate, Plotly chart |
