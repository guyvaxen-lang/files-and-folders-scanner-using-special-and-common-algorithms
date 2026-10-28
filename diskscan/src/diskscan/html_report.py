"""Self-contained interactive HTML treemap report."""
from __future__ import annotations

import json

from .scanner import DirNode


def _build(node: DirNode, total: int, min_frac: float, depth: int) -> dict:
    out = {"name": node.name, "value": node.size, "files": node.file_count}
    if depth <= 0 or not node.children:
        return out
    kids = sorted(node.children, key=lambda c: -c.size)
    children, small = [], 0
    for k in kids:
        if k.size >= total * min_frac:
            children.append(_build(k, total, min_frac, depth - 1))
        else:
            small += k.size
    own = node.size - sum(k.size for k in kids)
    if own > 0:
        children.append({"name": "(files in this folder)", "value": own, "files": 0})
    if small > 0:
        children.append({"name": "(small folders)", "value": small, "files": 0})
    children.sort(key=lambda d: -d["value"])
    out["children"] = children
    return out


def write_html(root: DirNode, path: str, *, depth: int = 6, min_fraction: float = 0.002) -> None:
    data = _build(root, max(root.size, 1), min_fraction, depth)
    data["name"] = root.path
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = _TEMPLATE.replace("__DATA__", blob)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>diskscan report</title>
<style>
:root{--bg:#fafaf9;--fg:#1c1917;--muted:#78716c;--border:#e7e5e4;--accent:#2563eb}
@media (prefers-color-scheme:dark){:root{--bg:#1c1917;--fg:#fafaf9;--muted:#a8a29e;--border:#44403c;--accent:#60a5fa}}
*{box-sizing:border-box}
body{margin:0;font:14px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--bg);color:var(--fg)}
header{padding:14px 20px;border-bottom:1px solid var(--border)}
h1{margin:0 0 4px;font-size:16px}
#crumbs{color:var(--muted);word-break:break-all}
.link{color:var(--accent);cursor:pointer}
#map{position:relative;height:calc(100vh - 110px);margin:12px 20px}
.cell{position:absolute;overflow:hidden;padding:6px 8px;color:#fff;border:2px solid var(--bg);border-radius:4px;font-size:12px}
.cell.drill{cursor:pointer}
.cell.drill:hover{filter:brightness(1.15)}
.cell b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cell span{opacity:.85}
</style>
</head>
<body>
<header><h1>diskscan</h1><div id="crumbs"></div></header>
<div id="map"></div>
<script id="data" type="application/json">__DATA__</script>
<script>
const data = JSON.parse(document.getElementById('data').textContent);
const map = document.getElementById('map'), crumbs = document.getElementById('crumbs');
let stack = [data];

const fmt = n => { const u=['B','KB','MB','GB','TB','PB']; let i=0;
  while (n >= 1024 && i < u.length-1) { n /= 1024; i++; }
  return (i ? n.toFixed(1) : n) + ' ' + u[i]; };

function squarify(items, x, y, w, h) {
  const out = [], total = items.reduce((s, d) => s + d.value, 0);
  if (!total) return out;
  const k = (w * h) / total;
  let i = 0;
  while (i < items.length) {
    const side = Math.min(w, h);
    const worst = (sum, arr) => {
      const mx = arr[0].value * k, mn = arr[arr.length-1].value * k;
      return Math.max(side*side*mx/(sum*sum), sum*sum/(side*side*mn));
    };
    let row = [items[i]], area = items[i].value * k, j = i + 1;
    while (j < items.length) {
      const cand = row.concat(items[j]), a2 = area + items[j].value * k;
      if (worst(a2, cand) <= worst(area, row)) { row = cand; area = a2; j++; } else break;
    }
    if (w >= h) {
      const rw = area / h; let yy = y;
      for (const d of row) { const dh = d.value * k / rw; out.push({d, x, y: yy, w: rw, h: dh}); yy += dh; }
      x += rw; w -= rw;
    } else {
      const rh = area / w; let xx = x;
      for (const d of row) { const dw = d.value * k / rh; out.push({d, x: xx, y, w: dw, h: rh}); xx += dw; }
      y += rh; h -= rh;
    }
    i = j;
  }
  return out;
}

function draw() {
  const node = stack[stack.length - 1];
  crumbs.replaceChildren();
  stack.forEach((n, i) => {
    const s = document.createElement('span');
    s.textContent = (i ? ' \u203a ' : '') + n.name;
    if (i < stack.length - 1) { s.className = 'link'; s.onclick = () => { stack = stack.slice(0, i+1); draw(); }; }
    crumbs.appendChild(s);
  });
  const total = document.createElement('span');
  total.textContent = '  \u2014 ' + fmt(node.value);
  crumbs.appendChild(total);

  map.replaceChildren();
  const kids = (node.children || []).filter(c => c.value > 0);
  squarify(kids, 0, 0, map.clientWidth, map.clientHeight).forEach(({d, x, y, w, h}, idx) => {
    const el = document.createElement('div');
    el.className = 'cell' + (d.children ? ' drill' : '');
    el.style.cssText = `left:${x}px;top:${y}px;width:${w}px;height:${h}px;background:hsl(${(idx*47)%360},45%,36%)`;
    const pct = (d.value / node.value * 100).toFixed(1);
    el.title = `${d.name}\n${fmt(d.value)} (${pct}%)` + (d.files ? `\n${d.files.toLocaleString()} files` : '');
    if (w > 60 && h > 36) {
      const b = document.createElement('b'); b.textContent = d.name;
      const s = document.createElement('span'); s.textContent = fmt(d.value) + ' \u00b7 ' + pct + '%';
      el.append(b, s);
    }
    if (d.children) el.onclick = () => { stack.push(d); draw(); };
    map.appendChild(el);
  });
}
window.addEventListener('resize', draw);
draw();
</script>
</body>
</html>
"""
