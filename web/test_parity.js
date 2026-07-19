/**
 * Parity test: verify the JS analytical core matches the Python core.
 *
 * Reads data.json (the aligned price series) and fixtures.json (Python-
 * computed success rates at a spread of holding periods and both bases),
 * then runs the JS functions and asserts the rates match.
 *
 * This runs in CI before every deploy. If it fails, the site does not
 * update, so the JS mirror can never silently drift from the Python core.
 *
 * Usage: node web/test_parity.js
 */

var fs = require("fs");
var path = require("path");
var core = require("./core.js");

var webDir = path.dirname(__filename);
var data = JSON.parse(fs.readFileSync(path.join(webDir, "data.json"), "utf8"));
var fixtures = JSON.parse(
  fs.readFileSync(path.join(webDir, "fixtures.json"), "utf8")
);

// sanity check: row counts must match
if (data.dates.length !== fixtures.row_count) {
  console.error(
    "Row count mismatch: data.json has " +
      data.dates.length +
      " rows, fixtures.json expects " +
      fixtures.row_count
  );
  process.exit(1);
}

var passed = 0;
var failed = 0;
var tolerance = 1e-9;

for (var i = 0; i < fixtures.fixtures.length; i++) {
  var fixture = fixtures.fixtures[i];
  var ratio = core.computeRatio(data.price_btc, data.price_gold, fixture.base);
  var profitable = core.computeWindows(ratio, fixture.period);
  var rate = core.calculateSuccessRate(profitable);

  var diff = Math.abs(rate - fixture.rate);
  if (diff < tolerance) {
    passed++;
  } else {
    console.error(
      "FAIL: base=" +
        fixture.base +
        " period=" +
        fixture.period +
        " expected=" +
        fixture.rate +
        " got=" +
        rate +
        " diff=" +
        diff
    );
    failed++;
  }
}

console.log("Parity: " + passed + " passed, " + failed + " failed");
if (failed > 0) {
  process.exit(1);
}
