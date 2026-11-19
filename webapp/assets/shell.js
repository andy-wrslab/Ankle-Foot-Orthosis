// Shared browser helpers for the AFO web app (loaded automatically by Dash).
(function () {
    // CiA 402 statusword -> drive state shown in the top bar and on the Motor
    // button border. The fault bit is what this drive reports while Safe Torque
    // Off is engaged (2026-11-19: 0x228 -> 0x260 the moment STO was released);
    // the statusword alone cannot tell STO from a real fault, so it is amber.
    window._afoDecodeStatus = function (sw) {
        if (sw & 0x0008) return {color: '#E69F00', text: 'Fault (STO?)', cls: 'sto', ready: false};
        if ((sw & 0x0002) && (sw & 0x0400)) return {color: '#009E73', text: 'Target reached', cls: 'ok', ready: true};
        if (sw & 0x0004) return {color: '#009E73', text: 'Operation enabled', cls: 'ok', ready: true};
        if (sw & 0x0002) return {color: '#E69F00', text: 'Switched on', cls: 'ready', ready: true};
        if (sw & 0x0001) return {color: '#E69F00', text: 'Ready', cls: 'ready', ready: true};
        if (sw & 0x0040) return {color: '#9CA3AF', text: 'Switch-on disabled', cls: 'off', ready: false};
        return {color: '#9CA3AF', text: 'Not ready', cls: 'off', ready: false};
    };

    // Called by the router callback when the visible page changes.
    window._afoShowPage = function (page) {
        window._afoPage = page;
        // plots that were hidden need a resize once they become visible
        setTimeout(function () { window.dispatchEvent(new Event('resize')); }, 60);
    };
})();
