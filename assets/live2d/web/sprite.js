// JChat Pet：Sprite 后端（Petdex 精灵图 8×9 网格）。
// 与 pet.js（Live2D 后端）实现完全相同的全局 API：
//   setExpression/setTalking/setGaze/setBubble/setBubbleVisible/setOverlayVisible/bounce/playTail
//   window.__takeSend/__takeEvents/__modelLoaded/__loadError
// Python 端零改动即可切换后端（config.companion.avatar_backend = "sprite" | "live2d"）。

var bubbleTTL = 30000;
window.__events = [];
window.__pendingSend = null;
window.__modelLoaded = false;
window.__loadError = '';

function post(ev) { window.__events.push(ev); }
function takeSend() { var s = window.__pendingSend; window.__pendingSend = null; return s; }
function takeEvents() { var e = window.__events; window.__events = []; return e; }

// ---------------- 精灵图元数据（vivimi-strict：1536×1872，帧 192×208） ----------------
// 行定义按视觉内容标注；帧数不对时改 ROWS 即可（tap_coords.log 可用于点击区校准）。
var FRAME_W = 192, FRAME_H = 208, COLS = 8;
// [行号, 帧数]
var ROWS = {
    idle: [0, 6],       // 站立+眨眼
    talk: [1, 8],       // 张嘴（说话口型近似）
    tongue: [2, 8],     // 吐舌蹦跳
    wave: [3, 4],       // 挥手
    happy: [4, 5],      // 吐舌喘气（开心）
    surprised: [5, 8],  // 惊吓含泪
    meh: [6, 6],        // 墨镜嫌弃脸
    cheer: [7, 6],      // 握拳欢呼
    smug: [8, 6],       // 得意/眯眼
};
// 表情预设 → 状态行（与 pet.js PRESETS 键对齐；celebrate 为 sprite 独有：工具完成后欢呼）
var EXPR_MAP = {
    idle: 'idle', happy: 'happy', thinking: 'smug', shy: 'meh',
    surprised: 'surprised', angry: 'meh', sad: 'surprised',
    tongue: 'tongue', sleepy: 'smug', talk: 'talk', celebrate: 'cheer',
};
var FPS_MS = 110;
var SCALE = 0.82;

var canvas = document.getElementById('canvas');
var ctx = canvas.getContext('2d');
var sheet = null;
var expr = 'idle';
var talking = false;
var oneShot = null;   // {row, frames, done} 一次性动画（playTail 等）
var rect = { x: 0, y: 0, w: 0, h: 0 }; // 绘制区（命中区按此缩放）
var frameIdx = 0;
var dragDir = null;   // 'left' | 'right' | null（拖动时播跑动动画并镜像）
var FACE = -1;        // 素材默认朝向：1=朝右。实测反了 → -1（朝左）

function curRow() {
    if (dragDir) return ROWS.tongue; // 拖动 = 跑动（用户主动意图，最高优先）
    if (oneShot) return ROWS[oneShot.row];
    if (talking && (expr === 'idle' || expr === 'happy')) return ROWS.talk;
    return ROWS[EXPR_MAP[expr]] || ROWS.idle;
}

function layout() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    var topZone = 170; // 顶部预留气泡区（与 Live2D 后端一致）
    var base = Math.min((window.innerHeight - topZone) / FRAME_H,
        window.innerWidth / FRAME_W);
    var s = base * SCALE;
    rect.w = FRAME_W * s;
    rect.h = FRAME_H * s;
    rect.x = (window.innerWidth - rect.w) / 2;
    rect.y = window.innerHeight - rect.h - 56; // 底部预留输入框高度，避免遮挡腿部
}
window.addEventListener('resize', layout);

var lastStep = 0;
function tick(ts) {
    requestAnimationFrame(tick);
    if (!sheet) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (ts - lastStep >= FPS_MS) {
        lastStep = ts;
        frameIdx++;
        if (oneShot && frameIdx >= oneShot.frames) oneShot = null;
    }
    var row = curRow();
    var frames = row[1];
    var i = frameIdx % frames;
    var sx = i * FRAME_W, sy = row[0] * FRAME_H;
    var flipped = (dragDir === 'left' && FACE === 1) || (dragDir === 'right' && FACE === -1);
    if (flipped) {
        ctx.save();
        ctx.translate(rect.x + rect.w, rect.y);
        ctx.scale(-1, 1);
        ctx.drawImage(sheet, sx, sy, FRAME_W, FRAME_H, 0, 0, rect.w, rect.h);
        ctx.restore();
    } else {
        ctx.drawImage(sheet, sx, sy, FRAME_W, FRAME_H, rect.x, rect.y, rect.w, rect.h);
    }
}

// ---------------- 表情 / 说话 / 动作 ----------------
function setExpression(name) {
    if (!ROWS[EXPR_MAP[name]] && name !== 'idle') return;
    expr = name;
    oneShot = null;
}
window.__setExpr = setExpression;

function setTalking(on) { talking = !!on; }

function setGaze(on) { /* sprite 无视线参数：no-op（保持 API 兼容） */ }

function playTail() {
    if (dragging) return; // 拖动期间不插挥手动画
    oneShot = { row: 'wave', frames: ROWS.wave[1] + 1 };
    frameIdx = 0;
}
window.__playTail = playTail;

function bounce() {
    canvas.style.transition = 'transform 0.12s';
    canvas.style.transform = 'translateY(-10px)';
    setTimeout(function () { canvas.style.transform = 'translateY(0)'; }, 140);
}

// ---------------- 命中区（相对绘制区 rect，比例坐标；tap_coords.log 可校准） ----------------
function _distToSegment(px, py, x1, y1, x2, y2) {
    var dx = x2 - x1, dy = y2 - y1;
    var l2 = dx * dx + dy * dy;
    var t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / l2));
    return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}
function _petHit(x, y) {
    var cx = rect.x + rect.w / 2;
    var areas = [];
    var headR = rect.h * 0.20, bodyR = rect.h * 0.18;
    var headCy = rect.y + rect.h * 0.28, bodyCy = rect.y + rect.h * 0.68;
    // 呆毛（优先级最高）：头顶正上方
    if (_distToSegment(x, y, cx, rect.y + rect.h * 0.06, cx - rect.w * 0.04, rect.y - rect.h * 0.02) <= rect.h * 0.05) areas.push('Ahoge');
    // 尾巴：左侧长条
    if (_distToSegment(x, y, rect.x + rect.w * 0.10, rect.y + rect.h * 0.75, rect.x + rect.w * 0.02, rect.y + rect.h * 0.88) <= rect.h * 0.05) areas.push('Tail');
    var dxh = x - cx, dyh = y - headCy;
    if (dxh * dxh + dyh * dyh <= headR * headR) areas.push('Head');
    var dxb = x - cx, dyb = y - bodyCy;
    if (dxb * dxb + dyb * dyb <= bodyR * bodyR) areas.push('Body');
    return areas;
}
window.__petHit = _petHit;

canvas.addEventListener('pointerdown', function (e) { /* 点击判定延后到 mouseup（区分拖动） */ });

// 右键菜单 / 拖拽 / 悬停（协议与 pet.js 一致）
document.addEventListener('contextmenu', function (e) {
    e.preventDefault();
    post({ type: 'menu' });
});
var dragging = false;
var pressed = false;
var pressXY = null;
var CLICK_MOVE_PX = 6; // 移动超过此距离判定为拖动，不触发点击

function _firePoke(x, y) {
    var areas = _petHit(x, y);
    if (!areas || areas.length === 0) return; // 点中透明区：忽略
    post({ type: 'tap-pos', x: Math.round(x), y: Math.round(y) });
    var region = areas.indexOf('Ahoge') >= 0 ? 'ahoge'
        : (areas.indexOf('Tail') >= 0 ? 'tail'
            : (areas.indexOf('Head') >= 0 ? 'head' : 'body'));
    post({ type: 'poke', region: region });
}

document.addEventListener('mousedown', function (e) {
    if (e.target.tagName === 'INPUT') return;
    dragging = true;
    pressed = true;
    pressXY = { x: e.clientX, y: e.clientY };
});
document.addEventListener('mousemove', function (e) {
    if (dragging) {
        post({ type: 'drag', dx: e.movementX, dy: e.movementY });
        if (e.movementX > 1) dragDir = 'right';
        else if (e.movementX < -1) dragDir = 'left';
    }
});
document.addEventListener('mouseup', function (e) {
    if (pressed) {
        pressed = false;
        var moved = pressXY ? Math.hypot(e.clientX - pressXY.x, e.clientY - pressXY.y) : 999;
        pressXY = null;
        if (moved <= CLICK_MOVE_PX) _firePoke(e.clientX, e.clientY); // 没怎么动 = 点击
    }
    dragging = false;
    dragDir = null; // 松手恢复原表情
});

// ---------------- 悬停 / 气泡 / 输入 ----------------
var overlay = document.getElementById('overlay');
var bubble = document.getElementById('bubble');
var input = document.getElementById('chatInput');
var collapseTimer = null;
var ttlTimer = null;

function showOverlay() { overlay.classList.add('visible'); }
function hideOverlay() {
    overlay.classList.remove('visible');
    post({ type: 'collapsed' });
}
document.addEventListener('mouseenter', function () { showOverlay(); });
document.addEventListener('mouseleave', function () {
    collapseTimer = setTimeout(function () {
        if (!overlay.matches(':hover') && !document.hasFocus()) hideOverlay();
    }, 1500);
});
input.addEventListener('focus', function () {
    if (collapseTimer) clearTimeout(collapseTimer);
    showOverlay();
});
input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        var v = input.value.trim();
        if (v) { window.__pendingSend = v; input.value = ''; }
    }
});

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

// ---------------- 加载 ----------------
function init() {
    layout();
    var params = new URLSearchParams(location.search);
    var base = params.get('avatar') || '/web/sprite/pets/vivimi';
    SCALE = parseFloat(params.get('scale')) || 0.82;
    layout();
    fetch(base + '/pet.json')
        .then(function (r) { return r.json(); })
        .then(function (meta) {
            sheet = new Image();
            sheet.onload = function () { window.__modelLoaded = true; };
            sheet.onerror = function (e) { window.__loadError = 'spritesheet load failed'; };
            sheet.src = base + '/' + (meta.spritesheetPath || 'spritesheet.webp');
        })
        .catch(function (err) { window.__loadError = String(err && err.message || err); });
    requestAnimationFrame(tick);
}
window.__takeSend = takeSend;
window.__takeEvents = takeEvents;
init();
