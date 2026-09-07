// JChat Pet：Live2D 渲染 + 表情预设（运行时参数）+ 交互（点击/连击/视线/拖拽/菜单）+ 气泡/输入。
// 与 Python 通过全局钩子通信：window.__takeSend() / window.__takeEvents() / window.* 控制函数。

var model = null;
var app = null;
var expr = 'idle';
var talking = false;
var gazeEnabled = true;
var bubbleTTL = 30000;
var inputVisible = false;
var hovered = false;
var lastMouseMove = 0;

window.__events = [];
window.__pendingSend = null;

function post(ev) { window.__events.push(ev); }
function takeSend() { var s = window.__pendingSend; window.__pendingSend = null; return s; }
function takeEvents() { var e = window.__events; window.__events = []; return e; }

// ---------------- 参数写入（数组直写，唯一有效路径） ----------------
function _idx(id) {
    var ids = model.internalModel.coreModel._parameterIds || [];
    return ids.indexOf(id);
}
function _setRaw(id, value) {
    var i = _idx(id);
    if (i >= 0) model.internalModel.coreModel._parameterValues[i] = value;
}

var PRESETS = {
    idle: {},
    happy: { ParamMouthOpenY: 0.5, ParamMouthForm: 1, ParamEyeLOpen: 0.8, ParamEyeROpen: 0.8 },
    thinking: { ParamAngleZ: 12, ParamEyeBallY: 0.6, ParamMouthOpenY: 0 },
    shy: { ParamCheek: 1, ParamMouthForm: 0.5 },
    surprised: { ParamJawOpen: 1, ParamMouthOpenY: 0.4, ParamEyeLOpen: 1, ParamEyeROpen: 1 },
    angry: { ParamBrowLAngle: 1, ParamBrowRAngle2: 1, ParamMouthOpenY: 0.4 },
    sad: { ParamMouthOpenY: 0.2, ParamEyeLOpen: 0.6, ParamEyeROpen: 0.6, ParamEyeBallY: -0.5, ParamCheek: 0.5 },
    tongue: { Param158: 1, ParamMouthOpenY: 0.3 },
    sleepy: { ParamEyeLOpen: 0.45, ParamEyeROpen: 0.45, ParamMouthForm: 0.2 },
    talk: { ParamMouthOpenY: 0.6, ParamMouthForm: 0.3 },
};

// 情绪尾巴：motion 管理器在此核心缺失 API 无法生效，改为数组直写实现"伸出-收回"摇尾节奏
var _tailTimer = null;
function playTail() {
    if (!model) return;
    if (_tailTimer) { clearInterval(_tailTimer); _tailTimer = null; }
    var seq = [0, 0.55, 0, 0.55, 0, 0.55, 0]; // 出-收摆动（半幅）
    var i = 0;
    _tailTimer = setInterval(function () {
        if (!model) { clearInterval(_tailTimer); _tailTimer = null; return; }
        var v = seq[i % seq.length];
        _setRaw('Param100', v);
        _setRaw('Param90', -v);
        i++;
        if (i >= seq.length * 2) {
            clearInterval(_tailTimer);
            _tailTimer = null;
            _setRaw('Param100', 0);
            _setRaw('Param90', 0);
        }
    }, 550);
}
window.__playTail = playTail;

function setExpression(name) {
    if (!model || !PRESETS.hasOwnProperty(name)) return;
    var ids = model.internalModel.coreModel._parameterIds || [];
    var defs = model.internalModel.coreModel._parameterDefaultValues || [];
    var prev = PRESETS[expr] || {};
    Object.keys(prev).forEach(function (id) {
        var i = ids.indexOf(id);
        if (i >= 0) model.internalModel.coreModel._parameterValues[i] = defs[i] != null ? defs[i] : 0;
    });
    var next = PRESETS[name];
    Object.keys(next).forEach(function (id) { _setRaw(id, next[id]); });
    if (name === 'happy') playTail();
    expr = name;
}
window.__setExpr = setExpression;

function setTalking(on) {
    talking = !!on;
    if (!talking) _setRaw('ParamMouthOpenY', 0);
}

function setGaze(on) { gazeEnabled = !!on; }

// 自动眨眼（手动控制：闭眼 300ms，间隔 4s）
var BLINK_CLOSE_MS = 300;
setInterval(function () {
    if (!model || expr === 'sad') return;
    _setRaw('ParamEyeLOpen', 0);
    _setRaw('ParamEyeROpen', 0);
    setTimeout(function () {
        _setRaw('ParamEyeLOpen', 1);
        _setRaw('ParamEyeROpen', 1);
    }, BLINK_CLOSE_MS);
}, 4000);

// 说话口型（数组直写）
setInterval(function () {
    if (!model || !talking) return;
    _setRaw('ParamMouthOpenY', Math.random() * 0.8 + 0.2);
}, 140);

// 视线跟随（3s 无移动回中）
document.addEventListener('mousemove', function (e) {
    lastMouseMove = Date.now();
    if (!gazeEnabled || !model) return;
    var nx = (e.clientX / window.innerWidth - 0.5) * 2;
    var ny = (e.clientY / window.innerHeight - 0.5) * 2;
    _setRaw('ParamEyeBallX', Math.max(-1, Math.min(1, nx)));
    _setRaw('ParamEyeBallY', Math.max(-1, Math.min(1, -ny)));
});
setInterval(function () {
    if (!model || !gazeEnabled) return;
    if (Date.now() - lastMouseMove > 3000) {
        _setRaw('ParamEyeBallX', 0);
        _setRaw('ParamEyeBallY', 0);
    }
}, 1000);

// ---------------- 点击 / 连击（圆形蒙版近似角色轮廓：头圆+身圆） ----------------
// 实测校准（10 边缘点拟合）：头心(241,397) r74、身心(246,448) r55、尾=长条胶囊
function _distToSegment(px, py, x1, y1, x2, y2) {
    var dx = x2 - x1, dy = y2 - y1;
    var l2 = dx * dx + dy * dy;
    var t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / l2));
    return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}
function _petHit(x, y) {
    var areas = [];
    // 呆毛（优先级最高）：头顶发梢横向胶囊 (232,309)-(277,308) 半径18（实测4点）
    if (_distToSegment(x, y, 232, 309, 277, 308) <= 18) areas.push('Ahoge');
    // 尾巴：长条胶囊 (272,463)-(330,475) 半径18
    if (_distToSegment(x, y, 272, 463, 330, 475) <= 18) areas.push('Tail');
    // 头 / 身
    var zones = [
        { cx: 241, cy: 397, r: 74, name: 'Head' },
        { cx: 246, cy: 448, r: 55, name: 'Body' },
    ];
    for (var i = 0; i < zones.length; i++) {
        var z = zones[i];
        var dx = x - z.cx, dy = y - z.cy;
        if (dx * dx + dy * dy <= z.r * z.r) areas.push(z.name);
    }
    return areas;
}

var lastPoke = 0, pokeCount = 0;
function _registerPetClick() {
    if (!model) return;
    model.interactive = true;
    model.on('pointertap', function (e) {
        post({ type: 'tap-pos', x: Math.round(e.data.global.x), y: Math.round(e.data.global.y) });
        var areas = _petHit(e.data.global.x, e.data.global.y);
        if (!areas || areas.length === 0) return; // 点中透明区：忽略
        var region = areas.indexOf('Ahoge') >= 0 ? 'ahoge'
            : (areas.indexOf('Tail') >= 0 ? 'tail'
                : (areas.indexOf('Head') >= 0 ? 'head' : 'body')); // Ahoge > Tail > Head > Body
        var now = Date.now();
        if (now - lastPoke < 2500) pokeCount++;
        else pokeCount = 1;
        lastPoke = now;
        if (pokeCount % 3 === 0) post({ type: 'combo', region: region });
        else post({ type: 'poke', region: region });
    });
}
window.__petHit = _petHit;

// 右键菜单事件
document.addEventListener('contextmenu', function (e) {
    e.preventDefault();
    post({ type: 'menu' });
});

// 拖拽（mousedown 在非输入区域）
var dragging = false;
document.addEventListener('mousedown', function (e) {
    if (e.target.tagName === 'INPUT') return;
    dragging = true;
});
document.addEventListener('mousemove', function (e) {
    if (dragging) post({ type: 'drag', dx: e.movementX, dy: e.movementY });
});
document.addEventListener('mouseup', function () { dragging = false; });

// ---------------- 悬停 / 气泡 / 输入 ----------------
var overlay = document.getElementById('overlay');
var bubble = document.getElementById('bubble');
var input = document.getElementById('chatInput');
var collapseTimer = null;
var ttlTimer = null;

function showOverlay() {
    overlay.classList.add('visible');
    inputVisible = true;
}
function hideOverlay() {
    overlay.classList.remove('visible');
    inputVisible = false;
    post({ type: 'collapsed' });
}
document.addEventListener('mouseenter', function () { hovered = true; showOverlay(); });
document.addEventListener('mouseleave', function () {
    hovered = false;
    collapseTimer = setTimeout(function () { if (!hovered && !document.hasFocus()) hideOverlay(); }, 1500);
});
input.addEventListener('focus', function () { hovered = true; if (collapseTimer) clearTimeout(collapseTimer); showOverlay(); });

function setBubble(text, tools) {
    bubble.innerHTML = '';
    var textNode = document.createElement('div');
    textNode.textContent = text;
    bubble.appendChild(textNode);
    if (tools && tools.length) {
        var row = document.createElement('div');
        row.className = 'tools';
        bubble.appendChild(row);
        tools.forEach(function (t) {
            var chip = document.createElement('span');
            chip.className = 'toolchip';
            chip.textContent = '🔧 ' + t.name + (t.status === 'done' ? ' ✓' : ' ✗');
            chip.addEventListener('click', function () {
                var out = bubble.querySelector('.output');
                if (out) { out.style.display = out.style.display === 'block' ? 'none' : 'block'; return; }
                var o = document.createElement('div');
                o.className = 'output';
                o.textContent = t.output_preview || '';
                bubble.appendChild(o);
            });
            row.appendChild(chip);
        });
    }
    var full = document.createElement('span');
    full.className = 'full';
    full.textContent = '查看全文 ↗';
    full.addEventListener('click', function () { post({ type: 'open_chat' }); });
    bubble.appendChild(full);
    bubble.classList.add('visible');
    if (ttlTimer) clearTimeout(ttlTimer);
    ttlTimer = setTimeout(function () { bubble.classList.remove('visible'); }, bubbleTTL);
    showOverlay();
}

function setBubbleVisible(on) {
    if (on) bubble.classList.add('visible');
    else bubble.classList.remove('visible');
}
function setOverlayVisible(on) {
    if (on) showOverlay();
    else hideOverlay();
}

input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        var v = input.value.trim();
        if (v) { window.__pendingSend = v; input.value = ''; }
    }
});

// 弹跳动画
function bounce() {
    var c = document.getElementById('canvas');
    c.style.transition = 'transform 0.12s';
    c.style.transform = 'translateY(-10px)';
    setTimeout(function () { c.style.transform = 'translateY(0)'; }, 140);
}

// ---------------- 加载模型 ----------------
function init() {
    app = new PIXI.Application({
        view: document.getElementById('canvas'),
        autoStart: true,
        resizeTo: window,
        transparent: true,
        backgroundAlpha: 0,
        preserveDrawingBuffer: true,
    });
    var modelUrl = new URLSearchParams(location.search).get('model');
    if (!modelUrl) { window.__loadError = 'no model url'; return; }
    PIXI.live2d.Live2DModel.from(modelUrl, { autoInteract: false })
        .then(function (m) {
            model = m;
            window.__model = m;
            app.stage.addChild(model);
            model.anchor.set(0.5, 0.5);
            resizeModel();
            _registerPetClick();
            window.__modelLoaded = true;
        })
        .catch(function (err) {
            window.__modelLoaded = false;
            window.__loadError = String(err && err.message || err);
        });
}
function resizeModel() {
    if (!model) return;
    var topZone = 170; // 顶部预留气泡区（含间隙）
    var avail = window.innerHeight - topZone;
    var s = avail / model.internalModel.originalHeight;
    model.scale.set(s);
    model.position.set(window.innerWidth * 0.5, topZone + avail * 0.5);
}
window.addEventListener('resize', resizeModel);
window.__modelLoaded = false;
window.__loadError = '';
window.__takeSend = takeSend;
window.__takeEvents = takeEvents;

// ---------------- 探测工具（表情调试用） ----------------
function probeClean() {
    if (!model) return;
    var core = model.internalModel.coreModel;
    var ids = core._parameterIds || [];
    var defs = core._parameterDefaultValues || [];
    for (var i = 0; i < ids.length; i++) {
        if (defs[i] != null) core._parameterValues[i] = defs[i];
    }
}
function probeSet(pairs) {
    probeClean();
    if (!model || !pairs) return;
    Object.keys(pairs).forEach(function (id) { _setRaw(id, pairs[id]); });
}
window.__probeClean = probeClean;
window.__probeSet = probeSet;
window.__probeSet2 = function (id, value, method) {
    var im = model.internalModel;
    if (method === 'arr') {
        var ids = im.coreModel._parameterIds || [];
        var idx = ids.indexOf(id);
        if (idx >= 0) im.coreModel._parameterValues[idx] = value;
    } else if (method === 'dict') {
        if (!im.parameters) im.parameters = {};
        im.parameters[id] = value;
    } else {
        im.setParameterValueById(id, value);
    }
    return method + ':' + id + '=' + value;
};
window.__probeRead = function (id) {
    var im = model.internalModel;
    var arr = null;
    var ids = im.coreModel._parameterIds || [];
    var idx = ids.indexOf(id);
    if (idx >= 0) arr = im.coreModel._parameterValues[idx];
    var via = 'n/a';
    try { via = im.getParameterValueById(id); } catch (e) { via = 'err'; }
    return JSON.stringify({ idx: idx, arr: arr, via: via, dict: (im.parameters || {})[id] });
};
window.__snap = function () {
    var c = document.getElementById('canvas');
    if (!c) return '';
    try { return c.toDataURL('image/png'); } catch (e) { return ''; }
};
init();
