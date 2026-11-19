// Shared, fault-tolerant parsing of SSE payloads (loaded automatically by Dash
// from assets/). Both the plot callback and the health-lamp callback call it,
// so each payload is parsed once. A payload that cannot be parsed returns null
// and is skipped on its own; the next one is handled normally.
(function () {
    var cache = { raw: null, parsed: null };
    var failures = 0;
    window._afoParseFailures = 0;
    window._afoParse = function (raw) {
        if (raw === cache.raw) {
            return cache.parsed;
        }
        var parsed = null;
        try {
            parsed = JSON.parse(raw);
        } catch (e) {
            failures += 1;
            window._afoParseFailures = failures;
            if (failures <= 5 || failures % 100 === 0) {
                console.error('[AFO] SSE payload could not be parsed; skipped (' + failures + ' so far)', e);
            }
            parsed = null;
        }
        cache.raw = raw;
        cache.parsed = parsed;
        return parsed;
    };
})();

// Fixed-format readout: fixed decimals, a sign slot that is always present
// (U+2212 minus or U+2007 figure space), '—' for missing/rejected values. The
// value box has a fixed width in ch (set in the layout), so chips never resize.
window._afoFmt = function (v, dec, width) {
    if (typeof v !== 'number' || !isFinite(v)) { return '\u2014'; }
    var s = Math.abs(v).toFixed(dec);
    if (s.length > width - 1) { return '\u2014'; }
    var neg = v < 0 && Number(s) !== 0;
    return (neg ? '\u2212' : '\u2007') + s;
};

// Motor button fill = drive status from the Speedgoat statusword, with the
// same states and colours as the original GUI (GUI\dash_app.py 890-913):
// fault -> #FF9E9E, switched on + target reached -> #8FE38F,
// ready to switch on -> #FFD280, anything else -> #CCCCCC.
window._afoMotorStyle = function (sw) {
    var c = '#CCCCCC';
    if (sw & 0x0008) { c = '#FF9E9E'; }
    else if ((sw & 0x0002) && (sw & 0x0400)) { c = '#8FE38F'; }
    else if (sw & 0x0001) { c = '#FFD280'; }
    return {backgroundColor: c, borderColor: c, color: '#1F1E1B'};
};
