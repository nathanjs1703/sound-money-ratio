/**
 * Sound Money Ratio: browser-side analytical core.
 *
 * Mirrors the arithmetic in sound_money_core.py exactly. These functions
 * operate on the already-aligned, already-forward-filled price arrays
 * shipped in data.json (alignment is done in Python at publish time, so
 * the epistemically loaded logic -- outer join, reindex, ffill, leading-NaN
 * trim -- never leaves Python).
 *
 * What lives here is only the downstream arithmetic: ratio construction,
 * shift-comparison for windows, mean for success rate, segment
 * detection for chart coloring and presentation facts. Parity with the Python core is verified
 * by test_parity.js before every deploy.
 */
/**
 * Presentation facts per base frame.
 * Mirrors sound_money_core.py's BASE_PRESENTATION.
 */
var BASE_PRESENTATION = {
  gold: {
    held_asset: "bitcoin",
    numerator: "BTC",
    denominator: "Gold",
    unit: "oz gold per BTC"
  },
  bitcoin: {
    held_asset: "gold",
    numerator: "Gold",
    denominator: "BTC",
    unit: "BTC per oz gold"
  }
};
/**
 * Compute the ratio in the chosen base's direction.
 * Mirrors align_and_compute_ratio's final ratio assignment.
 *
 * @param {number[]} priceBtc  - aligned daily BTC prices
 * @param {number[]} priceGold - aligned daily gold prices
 * @param {string}   base      - "gold" or "bitcoin"
 * @returns {number[]} ratio array, same length as inputs
 */
function computeRatio(priceBtc, priceGold, base) {
  var len = priceBtc.length;
  var ratio = new Array(len);
  if (base === "gold") {
    for (var i = 0; i < len; i++) {
      ratio[i] = priceBtc[i] / priceGold[i];
    }
  } else {
    for (var i = 0; i < len; i++) {
      ratio[i] = priceGold[i] / priceBtc[i];
    }
  }
  return ratio;
}

/**
 * Classify every valid holding-period window as profitable or not.
 * Mirrors compute_windows: a window is profitable when exit > entry.
 * Equivalent to ratio.shift(-N) > ratio in pandas.
 *
 * @param {number[]} ratio             - from computeRatio
 * @param {number}   holdingPeriodDays - days between entry and exit
 * @returns {boolean[]} profitable flag per valid window
 */
function computeWindows(ratio, holdingPeriodDays) {
  var len = ratio.length - holdingPeriodDays;
  var profitable = new Array(len);
  for (var i = 0; i < len; i++) {
    profitable[i] = ratio[i + holdingPeriodDays] > ratio[i];
  }
  return profitable;
}

/**
 * Fraction of windows that were profitable.
 * Mirrors calculate_success_rate: mean of a boolean array.
 *
 * @param {boolean[]} profitable - from computeWindows
 * @returns {number} between 0.0 and 1.0
 */
function calculateSuccessRate(profitable) {
  var count = 0;
  for (var i = 0; i < profitable.length; i++) {
    if (profitable[i]) count++;
  }
  return count / profitable.length;
}

/**
 * Detect contiguous runs of same profitability for chart coloring.
 * Each segment includes the next segment's first point so adjacent
 * fills share their boundary and single-point runs still render; the
 * borrowed point's flag is ignored since color reads from the run's start.
 * Mirrors generate_chart's segment logic:
 *   (profitable != profitable.shift()).cumsum()
 *
 * @param {string[]}  dates      - trimmed to valid window entries
 * @param {number[]}  ratio      - trimmed to valid window entries
 * @param {boolean[]} profitable - from computeWindows
 * @returns {{dates: string[], ratios: number[], profitable: boolean}[]}
 */
function computeSegments(dates, ratio, profitable) {
  var segments = [];
  var segStart = 0;
  for (var i = 1; i <= profitable.length; i++) {
    if (i === profitable.length || profitable[i] !== profitable[segStart]) {
      segments.push({
        dates: dates.slice(segStart, i + 1),
        ratios: ratio.slice(segStart, i + 1),
        profitable: profitable[segStart],
      });
      segStart = i;
    }
  }
  return segments;
}

// Node.js exports for parity testing; harmless in the browser
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    computeRatio,
    computeWindows,
    calculateSuccessRate,
    computeSegments,
    BASE_PRESENTATION,
  };
}
