# -*- coding:utf-8 -*-
"""实验：不按 1000x1000 方形拉伸，沿用 aiTap/aiLocate 的坐标思路做滑块拖拽。

对比两种截图方案下模型给出的缺口 x 坐标：
  A) natural: 保持宽高比的截图（aiLocate 同款，CSS 分辨率 1:1，不放大模型误差）
  B) square : 1000x1000 方形拉伸（当前 aiAct ReAct 循环的做法）

然后用 natural 方案的坐标执行 CDP 拖拽，验证落点精度。
不改框架代码；只 import 现有工具函数。

运行：
    ./.venv/bin/python drag_no_square_experiment.py
"""
from base64 import b64decode, b64encode
from io import BytesIO
from json import dumps
from pathlib import Path
from time import sleep

from drissionpage_ai import Chromium, ChromiumOptions
from drissionpage_ai.context import normalize_screenshot_to_css_pixels, cap_screenshot_for_model
from drissionpage_ai.locator import _interpret_model_bbox
from drissionpage_ai.model import OpenAICompatibleModel

from cdp_drag_experiment import cdp_drag
from demo_env import load_dotenv

DEBUG_DIR = Path(__file__).parent / 'debug_log'
URL = 'https://dun.163.com/trial/jigsaw'

LOCATE_SYSTEM = (
    'You locate UI elements in a web page screenshot. '
    'Return JSON only, no extra text.'
)
LOCATE_USER = (
    'This is a slider-captcha page. Find two things:\n'
    '1. handle: the draggable slider handle/button on the track below the puzzle image.\n'
    '2. gap: the jigsaw notch/hole inside the puzzle image that the piece must fill.\n'
    'The screenshot is {w}x{h} pixels. Return:\n'
    '{{"handle": [x1, y1, x2, y2], "gap": [x1, y1, x2, y2]}}\n'
    '- bboxes must use pixel coordinates of THIS {w}x{h} image.\n'
    '- If unsure, still give your best estimate.'
)


def center(bbox):
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def square_1000(screenshot_base64):
    """当前 ReAct 方案：非等比压成 1000x1000。"""
    from PIL import Image
    image = Image.open(BytesIO(b64decode(screenshot_base64))).convert('RGB')
    image = image.resize((1000, 1000), Image.LANCZOS)
    buf = BytesIO()
    image.save(buf, format='JPEG', quality=88)
    return b64encode(buf.getvalue()).decode('ascii'), 'jpeg'


def locate_both(model, image_b64, image_format, w, h, tag):
    result = model.complete_json(
        LOCATE_SYSTEM,
        LOCATE_USER.format(w=w, h=h),
        image_base64=image_b64, image_format=image_format,
        debug={'debug_dir': str(DEBUG_DIR), 'debug_model': True, 'prompt_name': tag})
    return result


def annotate(image_b64, boxes, path):
    from PIL import Image, ImageDraw
    image = Image.open(BytesIO(b64decode(image_b64))).convert('RGBA')
    draw = ImageDraw.Draw(image)
    colors = {'handle': (59, 130, 246, 255), 'gap': (34, 197, 94, 255)}
    for name, bbox in boxes.items():
        color = colors[name]
        draw.rectangle(tuple(bbox), outline=color, width=3)
        cx, cy = center(bbox)
        draw.line((cx - 8, cy, cx + 8, cy), fill=(235, 64, 52, 255), width=3)
        draw.line((cx, cy - 8, cx, cy + 8), fill=(235, 64, 52, 255), width=3)
    image.save(path, format='PNG')


def interpret(result, img_w, img_h, scale_x, scale_y, model_name):
    """aiTap 同款解释链路：_interpret_model_bbox 自动识别 css/normalized，
    再按 model_scale 均匀缩放回 CSS 视口坐标。返回 (handle_css, gap_css)。"""
    size = {'width': img_w, 'height': img_h}
    out = {}
    for key in ('handle', 'gap'):
        candidates = _interpret_model_bbox({'bbox': result[key]}, size, model_name=model_name)
        if not candidates:
            raise RuntimeError('无法解释 {} bbox: {}'.format(key, result[key]))
        box = candidates[0]
        out[key] = [box['left'] * scale_x, box['top'] * scale_y,
                    box['right'] * scale_x, box['bottom'] * scale_y]
    return out['handle'], out['gap']


def prepare_captcha(page):
    """复现嵌入式验证码的触发流程：点'嵌入式' tab -> 滚动到验证条 -> 悬停显示拼图。"""
    page.ele('text=嵌入式').click()
    sleep(2)
    bar = page.ele('text:向右拖动滑块填充拼图')
    bar.scroll.to_see()
    sleep(1)
    bar.hover()  # 鼠标留在验证条上，拼图才会显示
    sleep(2)


def main():
    load_dotenv()
    model = OpenAICompatibleModel()
    if not model.available:
        raise RuntimeError('请先在 .env 配置 OPENAI_API_KEY / BASE_URL / MODEL')
    print('model:', model.model)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    page = Chromium(ChromiumOptions(read_file=False)).latest_tab
    try:
        page.get(URL)
        page.set.window.max()
        page.wait.doc_loaded()
        sleep(3)  # 等页面渲染
        prepare_captcha(page)

        # ---- 截图：aiTap 同款链路（DPR 归一化 + 1080p 封顶，保持宽高比）----
        from drissionpage_ai.adapter import DrissionPageAIAdapter
        adapter = DrissionPageAIAdapter(page)
        metrics = adapter.get_metrics()
        normalized = normalize_screenshot_to_css_pixels(adapter.screenshot_base64(), metrics)
        capped = cap_screenshot_for_model(normalized)
        css_w = normalized['size']['width']
        css_h = normalized['size']['height']
        scale_x = css_w / capped['size']['width']   # 模型图 -> CSS 的换算比例
        scale_y = css_h / capped['size']['height']
        print('css viewport: {}x{}, model image: {}x{}, scale: {:.3f}/{:.3f}'.format(
            css_w, css_h, capped['size']['width'], capped['size']['height'], scale_x, scale_y))

        # ---- A) natural：原比例图直接问模型 ----
        res_natural = locate_both(model, capped['base64'], 'png',
                                  capped['size']['width'], capped['size']['height'],
                                  'natural_locate')
        print('natural result:', dumps(res_natural, ensure_ascii=False))
        annotate(capped['base64'], res_natural, DEBUG_DIR / 'nosquare_natural_annotated.png')
        handle_nat, gap_nat = interpret(res_natural, capped['size']['width'], capped['size']['height'],
                                        scale_x, scale_y, model.model)
        print('natural gap center (css):', center(gap_nat))

        # ---- B) square：同一张图压成 1000x1000 再问 ----
        sq_b64, sq_fmt = square_1000(capped['base64'])
        res_square = locate_both(model, sq_b64, sq_fmt, 1000, 1000, 'square_locate')
        print('square result:', dumps(res_square, ensure_ascii=False))
        annotate(sq_b64, res_square, DEBUG_DIR / 'nosquare_square_annotated.png')
        _, gap_sq = interpret(res_square, 1000, 1000,
                              css_w / 1000, css_h / 1000, model.model)
        print('square  gap center (css):', center(gap_sq))
        print('两方案缺口 x 相差: {:.1f} css px'.format(
            abs(center(gap_nat)[0] - center(gap_sq)[0])))

        # ---- C) 用 natural 方案坐标执行拖拽 ----
        hx, hy = center(handle_nat)
        gx, _ = center(gap_nat)
        print('drag handle ({:.0f},{:.0f}) -> ({:.0f},{:.0f})'.format(hx, hy, gx, hy))
        cdp_drag(page, (hx, hy), (gx, hy), path='curve')
        sleep(1.5)

        after = page.get_screenshot(as_base64=True, full_page=False)
        (DEBUG_DIR / 'nosquare_after_drag.png').write_bytes(b64decode(after))
        verdict = model.complete_text(
            'You judge slider captcha results. Answer JSON {"aligned": true/false, "note": "..."}.',
            'Is the jigsaw piece aligned into the gap (captcha solved)? Or is it offset/failed?',
            image_base64=after, image_format='png')
        print('after-drag verdict:', verdict)
    finally:
        page.quit()


if __name__ == '__main__':
    main()
