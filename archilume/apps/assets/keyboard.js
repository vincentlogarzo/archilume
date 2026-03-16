// Keyboard event capture for Dash editor
// Stores last keydown in a global variable; polled by Dash clientside callback.
window._lastKeyEvent = '';

document.addEventListener('keydown', function(e) {
    // Ignore if user is typing in an input/textarea
    var tag = e.target.tagName.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;

    window._lastKeyEvent = JSON.stringify({
        key: e.key,
        ctrl: e.ctrlKey,
        shift: e.shiftKey,
        alt: e.altKey,
        ts: Date.now()
    });
});

// Suppress right-click context menu on the viewport graph
document.addEventListener('contextmenu', function(e) {
    var graph = document.getElementById('viewport-graph');
    if (graph && graph.contains(e.target)) {
        e.preventDefault();
    }
});
