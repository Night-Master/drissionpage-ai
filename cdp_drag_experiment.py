# -*- coding:utf-8 -*-
"""实验：用原始 CDP Input.dispatchMouseEvent 实现 bbox -> bbox 拖拽。

不改框架代码，独立验证：
1. 模型返回的 0-1000 归一化 bbox 换算回 CSS 视口坐标（沿用 aiTapAt 的逆变换思路）；
2. CDP mousePressed -> 分段 mouseMoved -> mouseReleased 能否驱动
   典型的 mousedown/mousemove/mouseup 拖拽控件（滑块验证码同款事件模型）。

运行：
    ./.venv/bin/python cdp_drag_experiment.py
"""
from json import dumps
from pathlib import Path
from time import sleep, time

from DrissionPage import Chromium, ChromiumOptions

HTML = '''<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>CDP drag experiment</title>
<style>
  body { font-family: sans-serif; margin: 40px; }
  #track { position: relative; width: 600px; height: 80px; background: #eee;
           border: 1px solid #ccc; }
  #handle { position: absolute; left: 10px; top: 15px; width: 50px; height: 50px;
            background: #4a90d9; border-radius: 6px; cursor: grab; }
  #drop-zone { position: absolute; left: 480px; top: 0; width: 120px; height: 80px;
               background: rgba(46, 204, 113, .3); border: 2px dashed #27ae60;
               box-sizing: border-box; }
  #status { margin-top: 16px; font-size: 14px; white-space: pre; }
</style></head>
<body>
  <h3>把蓝色滑块拖到绿色虚线框</h3>
  <div id="track">
    <div id="drop-zone"></div>
    <div id="handle"></div>
  </div>
  <div id="status">waiting</div>
  <script>
    const handle = document.getElementById('handle');
    const status = document.getElementById('status');
    const events = [];           // 记录事件序列，验证 CDP 事件是否被页面收到
    let dragging = false;
    let offsetX = 0;

    function log(type, x, y) {
      events.push({type, x: Math.round(x), y: Math.round(y), t: Date.now()});
      status.textContent = 'events: ' + events.map(e => e.type).join(' -> ')
        + '\\nhandle.left = ' + handle.style.left;
    }

    handle.addEventListener('mousedown', e => {
      dragging = true;
      offsetX = e.clientX - handle.getBoundingClientRect().left;
      log('mousedown', e.clientX, e.clientY);
      e.preventDefault();
    });
    document.addEventListener('mousemove', e => {
      if (!dragging) return;
      const trackLeft = document.getElementById('track').getBoundingClientRect().left;
      handle.style.left = (e.clientX - trackLeft - offsetX) + 'px';
      log('mousemove', e.clientX, e.clientY);
    });
    document.addEventListener('mouseup', e => {
      if (!dragging) return;
      dragging = false;
      log('mouseup', e.clientX, e.clientY);
      const hr = handle.getBoundingClientRect();
      const zr = document.getElementById('drop-zone').getBoundingClientRect();
      const ok = hr.left >= zr.left && hr.right <= zr.right;
      status.textContent += '\\nDROP ' + (ok ? 'SUCCESS' : 'MISS');
    });
    // 暴露给脚本读取
    window.__events = events;
  </script>
</body>
</html>
'''


def get_css_bbox(page, selector):
    """读取元素的 CSS 视口 bbox，模拟模型输出前换算成 0-1000 归一化坐标。"""
    raw = page.run_js(
        'const r = document.querySelector("{sel}").getBoundingClientRect();'
        'return JSON.stringify({{bbox:[r.left,r.top,r.right,r.bottom],'
        ' vw: window.innerWidth, vh: window.innerHeight}});'.format(sel=selector))
    import json
    return json.loads(raw)


def norm1000_to_css(bbox, vw, vh):
    """0-1000 归一化 bbox -> CSS 视口坐标（与 aiTapAt 内部换算同构）。"""
    x1, y1, x2, y2 = [float(v) for v in bbox]
    return (x1 / 1000 * vw, y1 / 1000 * vh, x2 / 1000 * vw, y2 / 1000 * vh)


def _ease_in_out(t):
    return t * t * (3 - 2 * t)


def make_waypoints(from_xy, to_xy, steps=25, path='linear', curve_ratio=0.2):
    """生成拖拽路径点。path='linear' 直线；'curve' 二次贝塞尔弧线，
    控制点沿中垂线偏移 curve_ratio * 距离，方向随机。"""
    from math import hypot
    from random import uniform
    sx, sy = from_xy
    tx, ty = to_xy
    dx, dy = tx - sx, ty - sy
    dist = hypot(dx, dy) or 1.0
    if path == 'curve':
        # 垂直方向单位向量 * 随机方向 * 偏移量
        sign = 1 if uniform(0, 1) > 0.5 else -1
        offset = dist * curve_ratio * sign
        cx, cy = (sx + tx) / 2 - dy / dist * offset, (sy + ty) / 2 + dx / dist * offset
    points = []
    for i in range(1, steps + 1):
        t = _ease_in_out(i / steps)
        if path == 'curve':
            # 二次贝塞尔：B(t) = (1-t)^2*P0 + 2(1-t)t*C + t^2*P1
            u = 1 - t
            x = u * u * sx + 2 * u * t * cx + t * t * tx
            y = u * u * sy + 2 * u * t * cy + t * t * ty
        else:
            x = sx + dx * t
            y = sy + dy * t
        points.append((x, y))
    return points


def cdp_drag(page, from_xy, to_xy, steps=25, duration=0.6, path='linear', curve_ratio=0.2):
    """原始 CDP 拖拽：mousePressed -> steps 段 mouseMoved -> mouseReleased。

    Input.dispatchMouseEvent 的 x/y 就是 CSS 视口坐标（DIP），无需 DPR 换算。
    path: 'linear' 直线滑动 | 'curve' 贝塞尔曲线滑动。
    """
    sx, sy = from_xy
    tx, ty = to_xy
    page.run_cdp_loaded('Input.dispatchMouseEvent', type='mouseMoved',
                        x=sx, y=sy, button='none', buttons=0)
    page.run_cdp_loaded('Input.dispatchMouseEvent', type='mousePressed',
                        x=sx, y=sy, button='left', buttons=1, clickCount=1)
    sleep(0.05)
    interval = duration / steps
    for x, y in make_waypoints(from_xy, to_xy, steps=steps, path=path,
                               curve_ratio=curve_ratio):
        page.run_cdp_loaded('Input.dispatchMouseEvent', type='mouseMoved',
                            x=x, y=y, button='left', buttons=1)
        sleep(interval)
    page.run_cdp_loaded('Input.dispatchMouseEvent', type='mouseReleased',
                        x=tx, y=ty, button='left', buttons=0, clickCount=1)


def max_lateral_deviation(from_xy, to_xy, points):
    """轨迹点到首尾连线的最大垂直距离，用来区分直线/曲线轨迹。"""
    from math import hypot
    sx, sy = from_xy
    tx, ty = to_xy
    dx, dy = tx - sx, ty - sy
    dist = hypot(dx, dy) or 1.0
    return max(abs(dy * x - dx * y + tx * sy - ty * sx) / dist for x, y in points)


def run_one(page, html_url, path):
    """用指定路径模式跑一遍拖拽，返回 (状态文本, 最大横向偏移)。"""
    import json
    page.get(html_url)
    sleep(0.5)

    # 1) 取源/目标 bbox（CSS 视口坐标），模拟模型视角转成 0-1000
    src = get_css_bbox(page, '#handle')
    dst = get_css_bbox(page, '#drop-zone')

    src_norm = [v / src['vw'] * 1000 if i % 2 == 0 else v / src['vh'] * 1000
                for i, v in enumerate(src['bbox'])]
    dst_norm = [v / dst['vw'] * 1000 if i % 2 == 0 else v / dst['vh'] * 1000
                for i, v in enumerate(dst['bbox'])]

    # 2) 逆变换回 CSS 坐标并取中心点（工具真正执行时的路径）
    sx1, sy1, sx2, sy2 = norm1000_to_css(src_norm, src['vw'], src['vh'])
    dx1, dy1, dx2, dy2 = norm1000_to_css(dst_norm, dst['vw'], dst['vh'])
    from_xy = ((sx1 + sx2) / 2, (sy1 + sy2) / 2)
    to_xy = ((dx1 + dx2) / 2, (dy1 + dy2) / 2)

    # 3) CDP 拖拽
    started = time()
    cdp_drag(page, from_xy, to_xy, path=path)
    sleep(0.3)

    # 4) 验证：事件序列 + 落点判定 + 轨迹形状
    events = json.loads(page.run_js('return JSON.stringify(window.__events)'))
    status = page.run_js('return document.getElementById("status").textContent')
    moves = [(e['x'], e['y']) for e in events if e['type'] == 'mousemove']
    deviation = max_lateral_deviation(from_xy, to_xy, moves) if moves else 0.0
    types = [e['type'] for e in events]
    assert 'mousedown' in types and 'mouseup' in types, 'CDP 事件未被页面接收'
    assert 'DROP SUCCESS' in status, '[{}] 拖拽未落入目标区域'.format(path)
    print('[{path}] from {f} to {t} | {n} moves | 耗时 {sec:.2f}s | '
          '轨迹最大横向偏移 {dev:.1f}px | DROP SUCCESS'.format(
              path=path, f=from_xy, t=to_xy, n=len(moves),
              sec=time() - started, dev=deviation))
    return status, deviation


def main():
    html_path = Path(__file__).parent / 'debug_log' / 'cdp_drag_test_page.html'
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(HTML, encoding='utf-8')

    page = Chromium(ChromiumOptions(read_file=False).headless(False)).latest_tab
    try:
        html_url = 'file://' + str(html_path)
        _, linear_dev = run_one(page, html_url, 'linear')
        _, curve_dev = run_one(page, html_url, 'curve')

        dist = 505.0  # from_xy -> to_xy 的大致水平距离
        assert linear_dev < 5.0, '直线轨迹偏移过大: {:.1f}px'.format(linear_dev)
        assert curve_dev > dist * 0.1, '曲线轨迹弯曲不明显: {:.1f}px'.format(curve_dev)
        print('\n✅ 实验通过：直线滑动与贝塞尔曲线滑动均可由 CDP 完成，轨迹形状符合预期')
    finally:
        page.quit()


if __name__ == '__main__':
    main()
