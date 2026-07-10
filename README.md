# Bitcoin over Gold Windows

#### Video Demo: [CS50P Final Project - Bitcoin Over Gold Windows](https://youtu.be/G4X1AkcEQB0)

#### Description: Historical analysis of how often bitcoin has outperformed gold over user-specified holding periods.

### Project Overview

This project uses Python to answer a simple question: if I own gold and I am thinking about buying bitcoin with it and holding it for a while, what are the chances I'll end up with more gold than I started with? The future is opaque to us, but we can look at the history. For every possible day in the past where someone could have made this trade, this tool checks whether holding bitcoin for the chosen length of time would have left them ahead or behind. The ratio or percentage that came out ahead is the answer the tool gives you.

Most analysis involving bitcoin or gold is measured in dollars. However, with constant historical debasement distorting the real economic signal I feel it is more instructive to see the direct relationship between these two important hard monetary primitives. Thus the non-dollar-centric framing is an intentional design philosophy.

### How to use it

##### Setup

1. Receive the project (cloned or downloaded)
2. `cd` into the project directory
3. Make a fresh virtual environment with `python3 -m venv .venv` and `source .venv/bin/activate`
4. Execute a `pip install -r requirements.txt` to get all the necessary third-party packages not in Python's standard library.

##### Running the tool

1. Once those are installed successfully then execute `python3 project.py <days>` in the terminal, where `<days>` is the integer number of days for the desired holding period. If you do not enter an argument the tool will use the pre-selected default of 180 days.
2. If this is your first time to use the tool then first it will download the price data CSV files in a folder called cache from the Yahoo Finance API. This will be evident by the `[*****100%*****] 1 of 1 completed`  (which are yfinance's progress bars) printed and by the appearance of the cache folders and the price data CSV files. If you have these files already and it has been less than the configured cache freshness window since their download then the tool will use the cached files instead of hitting the API and re-downloading them.
3. Next you will see the `Historical Success Rate: XX.X%` and `Chart saved to btc-gold-chart.html and opened in your browser` printed in the terminal.
4. Finally and most importantly, the BTC/Gold Ratio Chart will automatically be opened in your browser and also saved as `btc-gold-chart.html` in the project folder. If it doesn't open automatically, open the file manually. 

### Interpreting the results

In the chart you will see the entire BTC/Gold ratio over the available history, going back to the earliest date the bitcoin data provider has data, typically around 2014, up to the present, or the latest data provided, minus the selected holding period. The area under each point on the line is colored green if a window starting on that date was profitable, or red if not. The Historical Success Rate at the top of this chart and printed to the terminal is simply the portion of this time that was profitable or green. One may understand this to be a rough probability of being profitable over this holding period starting today and going into the future based on this past data, if past trends roughly continue (see Known limitations).

### File descriptions

##### project.py

The main project file project.py is a python script that consists of:
- The import section (Python Standard Library and third-party)
- Constants
- 6 custom functions: 
    - `fetch_price_data`
    - `align_and_compute_ratio`
    - `compute_windows`
    - `calculate_success_rate`
    - `amend_ratio_with_profitability`
    - `generate_chart`
- `main`
- the usual `if __name__ == "__main__":` guard

The 7 functions are organized with `main` at the bottom orchestrating and calling the other 6 custom functions.

The architectural flow of the script follows:
 **data → analysis → visualization**
 
 Where **data** consists of: 
 - `fetch_price_data`
 
 **analysis** consists of:
 - `align_and_compute_ratio`
 - `compute_windows`
 - `calculate_success_rate`
 - `amend_ratio_with_profitability`
 
 And finally **visualization** is accomplished by:
 - `generate_chart`.

##### test_project.py

The project file for testing project.py is test_project.py.

This file tests: 
- `fetch_price_data` with one test
- `align_and_compute_ratio` with two tests
- `compute_windows` with four tests
- `calculate_success_rate` with two tests
- `amend_ratio_with_profitability` with one test

for a total of 10 tests across five of the six custom functions. `main` and `generate_chart` are excluded because they only produce side effects. `fetch_price_data` is tested only for its invalid-asset error, since its main job hits the API.

To run the tests with project.py and test_project.py in your project folder, run `pytest` in the terminal from this folder.

##### requirements.txt

This file, requirements.txt, is a simple text document listing the project's required third-party packages: `pandas`, `yfinance`, `plotly`, and `pytest`. 

It can be installed with the instructions in "How to use it" above.

##### cache/

Once the script runs, it will create a cache/ folder in the project folder and download bitcoin_prices.csv and gold_prices.csv into this cache/ folder as a place to store these CSV files for use with the program. 

### Function by function walkthrough

##### `fetch_price_data`

Takes the str either `"bitcoin"` or `"gold"` delivered in `main` and produces a pandas DataFrame with index on Date and a price column. I used a dictionary to organize the look up of the respective assets in Yahoo Finance. Uses a CSV cache to handle data freshness (see Design Decisions).

##### `align_and_compute_ratio`

Takes the 2 pandas price series indexed on dates, joins them on date, reindexes on a continuous date range, forward-fills gaps (see Design Decisions), drops the earlier rows where bitcoin data doesn't yet exist and outputs the combined DataFrame with both assets and ratio of bitcoin over gold.

##### `compute_windows`

Takes the combined DataFrame with prices and ratio and along with the given or default holding_period_days gives a whole new DataFrame with entry/exit date and ratio and whether that change in ratio was profitable or not as a bool. Used a for loop and the handy ability to take a dictionary and turn it into a pandas DataFrame to build the compute windows output DataFrame. See design decisions for an explanation of the `holding_period_days >= (len(ratio_df) - 1)` choice.

##### `calculate_success_rate`

This function very simply takes the "profitable" column from the `compute_windows` DataFrame and takes an average of those bools giving the ratio of them that are true. 

##### `amend_ratio_with_profitability`

This function takes our two main DataFrames so far `ratio_df` and `windows_df` and does some trimming to account for the holding period, a reindex and then adds the `"profitable"` column from `windows_df` to `ratio_df` and then returns `ratio_df`.

##### `generate_chart`

The sort of grand finale function takes many of the previous outputs, `ratio_df`, `output_path`, `holding_period_days`, and `success_rate` and uses them to make a chart with plotly.graph_objects. First it segments ratio_df in a way that is particular to how the chart is built. (See design decisions). Then after making the figure it does a color fill for each segment to create the instant visual understanding of the profit and loss chart. Finally finishing out with titles and saving the chart to an HTML in the output path.

##### `main`

Orchestrates the flow:
- Parses the command line arguments
- Handles the no-argument default
- Calls the functions in order
- Prints results
- Opens the chart
- Handles errors

### Design decisions

**Forward-fill for gaps.** In `align_and_compute_ratio` there were several issues and decisions worked out in development for this function. First, the issue that gold is not traded on the weekend and so has no weekend price data where bitcoin is and does. After considering back fill, back and forward fill and forward fill, this was resolved with `ffill()`. Next, during development it was discovered that occasionally one of the data providers (usually bitcoin) gave data that was missing a day, usually the last or second to last day. This was resolved along with the gold weekend issue together as one with the `ffill()`, first by reindexing to a continuous date range to account for any missing days, and then with forward fill. So why forward fill? The assets data is forward-filled for occasional missing days from the data provider, on the same epistemic-conservatism principle as gold weekend handling: this tool propagates the last known price rather than fabricating or interpolating. And finally, because the bitcoin data only goes back to 2014 with Yahoo Finance and the asset itself only goes back to 2008 or 2009, and the gold data from Yahoo Finance goes back to 2000, this tool needed a practical way to pair that for one-to-one comparison and so the `.dropna()` method cuts off the older unused gold data.

**Caching and freshness.** In `fetch_price_data` the cache folder along with the freshness conditional block is for two purposes. First, to reduce hitting the API too frequently during the writing process and secondly, so that once the script is complete and ships it hits the API only as often as needed. That was made easy by creating the CACHE_MAX_AGE_IN_DAYS constant at the top of the script which I mostly kept at 7 days and then reduced to 3 days and then 1 day to ship. The bitcoin_prices.csv and gold_prices.csv from Yahoo Finance only add one price per day and so for the vast majority of use cases a date range that is fresh up to a few days is just as useful as one that hits the API every day or even worse 30 times a day.

**Vectorization vs. loop.** During initial development I used a loop version of `compute_windows` in keeping with my knowledge at the time. But to pave the way for further development it was necessary to vectorize it with `.shift(-N)`. I ensured the loops behavior with a characterization test (hand-traced across holding periods, including ties), then proved the vectorized version byte-identical on the full real dataset before removing the loop. One caveat worth noting: this vectorized computation is
equivalent to a calendar-day exit lookup only because `ratio_df` has a dense daily index (one row per calendar day, guaranteed upstream by `align_and_compute_ratio`'s reindex+ffill).

**yfinance.** I used yfinance for this project because it offered a decently thorough data set for both bitcoin and gold that was free, making the tool more widely available to anyone who may use it.

**Holding-period guard.** The decision for the `holding_period_days >= (len(ratio_df) - 1)` choice was ultimately a user interface decision. The filter will allow only `holding_period_days` of `len(ratio_df) - 2` or less. The choice may at first seem odd or even an error in judgment since a window removed ratio_df needs only one day remaining to technically pass without a `ValueError`. However, when the chart is produced it needs to contain at least two days to meaningfully display the change of ratio and color fill. 

**Segment-based chart coloring.** In `generate_chart` the original plan was to use a `where()` based NaN masking approach (one green trace, one red trace, each with `NaN` where the other color applies) that I found that is sometimes called the "NaN trick" that would work for `fill="tozeroy"`. This did not work and is a known and documented Plotly.js rendering bug. It was filling the entire area with brown instead of red and green segments. So instead I searched and found this technique: break the DataFrame into segments and then detect same-color runs with `(profitable != profitable.shift()).cumsum()`, then add one filled go.Scatter trace per segment.

### Known limitations

- Data only goes back to September 2014 due to Yahoo Finance's coverage, but Bitcoin's history goes all the way back to 2008/2009 so we are missing some data that some may find relevant. The value of this early data to the tool is debatable since Bitcoin was in an early adoption phase and gold wasn't.
- Occasional missing days handled by forward-fill. This inherently is data lossy and reduces validity of the information the tool can give when it is used at the day to day level.
- The bitcoin over gold ratio is constructed by dividing two USD-mediated series. Small direct markets exist trading bitcoin to tokenized gold, but there is no appreciably large native market where bitcoin trades directly against physical spot gold. 
- The tool depends on yfinance so transient outages would cause the program to fail with an API error.
- As discussed in "Interpreting the results" the percentage given as "Historical Success Rate" is only a loose proxy for the future probability of profitability. That predictive value for decision making is the purpose of the tool but is conditional on the future resembling the past. (_This is not financial advice._)
