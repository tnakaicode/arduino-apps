"""
画像のピント（シャープネス）判定スクリプト
ラプラシアン分散法を使用してブレを検出する
"""

import cv2
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def calc_laplacian_variance(image: np.ndarray) -> float:
    """ラプラシアン分散値を計算する（値が大きいほどシャープ）"""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    return laplacian.var()


def calc_tenengrad(image: np.ndarray) -> float:
    """Tenengrad法（Sobelフィルタのエネルギー）でシャープネスを計算する"""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    return np.mean(gx**2 + gy**2)


def judge_focus(image_path: str, threshold: float = 100.0,
                roi: tuple | None = None) -> dict:
    """
    画像のピントを判定する

    Parameters
    ----------
    image_path : str
        判定する画像ファイルのパス
    threshold : float
        ラプラシアン分散のしきい値（デフォルト100）
        値が小さいほど判定が厳しくなる
    roi : tuple | None
        注目領域 (x, y, w, h)。None の場合は画像全体を使用。
        テキストオーバーレイなど判定に不要な領域を除外するために使う。

    Returns
    -------
    dict
        判定結果を含む辞書
    """
    img = cv2.imread(str(image_path))
    if img is None:
        raise FileNotFoundError(f"画像を読み込めません: {image_path}")

    h, w = img.shape[:2]
    if roi is not None:
        x, y, rw, rh = roi
        x2 = min(x + rw, w)
        y2 = min(y + rh, h)
        x, y = max(x, 0), max(y, 0)
        crop = img[y:y2, x:x2]
        roi = (x, y, x2 - x, y2 - y)  # クリップ後の実寸に更新
    else:
        crop = img

    lap_var = calc_laplacian_variance(crop)
    tenengrad = calc_tenengrad(crop)
    is_focused = lap_var >= threshold

    result = {
        "path": str(image_path),
        "roi": roi,
        "laplacian_variance": lap_var,
        "tenengrad": tenengrad,
        "threshold": threshold,
        "is_focused": is_focused,
        "judgment": "ピントOK (SHARP)" if is_focused else "ピントNG (BLURRY)",
    }
    return result


def put_text_ja(img_bgr: np.ndarray, text: str, pos: tuple,
                font_size: int, color_bgr: tuple) -> np.ndarray:
    """日本語対応テキスト描画（Pillow使用）"""
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)
    draw = ImageDraw.Draw(pil_img)

    # Windowsの日本語フォントを優先して探す
    font_candidates = [
        "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
        "C:/Windows/Fonts/YuGothM.ttc",
    ]
    font = None
    for path in font_candidates:
        if Path(path).exists():
            font = ImageFont.truetype(path, font_size)
            break
    if font is None:
        font = ImageFont.load_default()

    r, g, b = color_bgr[2], color_bgr[1], color_bgr[0]
    draw.text(pos, text, font=font, fill=(r, g, b))
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def visualize(image_path: str, result: dict) -> None:
    """判定結果をオーバーレイ表示する"""
    img = cv2.imread(str(image_path))
    h, w = img.shape[:2]

    # 画像の下に黒帯を追加してテキスト領域を確保
    bar_h = 80
    canvas = np.zeros((h + bar_h, w, 3), dtype=np.uint8)
    canvas[:h, :] = img

    color = (0, 255, 0) if result["is_focused"] else (0, 0, 255)
    lap_text = f"Laplacian var: {result['laplacian_variance']:.1f}  (threshold: {result['threshold']})"
    label = "ピントOK (SHARP)" if result["is_focused"] else "ピントNG (BLURRY)"

    canvas = put_text_ja(canvas, label,    (10, h + 4),  32, color)
    canvas = put_text_ja(canvas, lap_text, (10, h + 44), 22, (255, 255, 0))

    # ROIがあれば矩形を描画
    if result["roi"] is not None:
        x, y, rw, rh = result["roi"]
        cv2.rectangle(canvas, (x, y), (x + rw, y + rh), (0, 200, 255), 2)
        canvas = put_text_ja(canvas, "ROI", (x + 4, y + 4), 18, (0, 200, 255))

    cv2.imshow("Focus Check", canvas)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def main():
    # ===== ここを変更 =====
    image_path = r"C:\Users\tnakai\Downloads\camera_20260508_184837.png"
    threshold = 100.0          # しきい値：小さくすると厳しくなる

    # ROIを画像中央・サイズ1/4に自動設定
    _img = cv2.imread(image_path)
    _h, _w = _img.shape[:2]
    _rw, _rh = _w // 2, _h // 2          # 幅・高さそれぞれ1/2 → 面積1/4
    roi = (_w // 4, _h // 4, _rw, _rh)   # 中央に配置
    # ======================

    result = judge_focus(image_path, threshold, roi=roi)

    print("=" * 50)
    print(f"ファイル           : {result['path']}")
    print(f"ROI                : {result['roi']}")
    print(f"ラプラシアン分散   : {result['laplacian_variance']:.2f}")
    print(f"Tenengrad          : {result['tenengrad']:.2f}")
    print(f"しきい値           : {result['threshold']}")
    print(f"判定結果           : {result['judgment']}")
    print("=" * 50)

    visualize(image_path, result)


if __name__ == "__main__":
    main()
