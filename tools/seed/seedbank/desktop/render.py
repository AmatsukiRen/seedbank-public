from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageColor, ImageDraw, ImageFilter


SUPERSAMPLE = 4


def _surface(size, background):
    return Image.new("RGBA", tuple(length * SUPERSAMPLE for length in size), background)


def _finish(image, size):
    return image.resize(size, Image.Resampling.LANCZOS)


def mix_color(first, second, amount):
    first_rgb = ImageColor.getrgb(first) if isinstance(first, str) else first[:3]
    second_rgb = ImageColor.getrgb(second) if isinstance(second, str) else second[:3]
    return tuple(round(start + (end - start) * amount) for start, end in zip(first_rgb, second_rgb))


@lru_cache(maxsize=96)
def _panel_skin(background, fill, border, shadow, radius, border_width, glaze, refraction, soft_shadow):
    inset = radius + 6
    size = (inset * 2 + 1, inset * 2 + 1)
    image = _surface(size, background)
    draw = ImageDraw.Draw(image)
    scale = SUPERSAMPLE
    shadow_layer = _surface(size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow_layer).rounded_rectangle(
        (2 * scale, 4 * scale, (size[0] - 3) * scale, (size[1] - 2) * scale),
        radius=radius * scale, fill=shadow)
    image.alpha_composite(shadow_layer.filter(ImageFilter.GaussianBlur(scale)) if glaze or soft_shadow else shadow_layer)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2 * scale, 2 * scale, (size[0] - 3) * scale, (size[1] - 5) * scale),
                           radius=radius * scale, fill=fill, outline=border, width=border_width * scale)
    if glaze:
        rim_inset = (3 + border_width) * scale
        face = Image.new("L", image.size)
        bounds = (rim_inset, rim_inset, image.width - rim_inset - scale, image.height - rim_inset - 3 * scale)
        inner_radius = max(0, radius * scale - rim_inset + 2 * scale)
        ImageDraw.Draw(face).rounded_rectangle(bounds, radius=inner_radius, fill=255)
        wash = _surface(size, fill)
        wash_draw = ImageDraw.Draw(wash)
        for vertical in range(min(image.height, 9 * scale)):
            strength = max(0, 1 - (vertical / scale - 3) / 6) * .35
            wash_draw.line((0, vertical, image.width, vertical), fill=mix_color(fill, glaze, strength))
        image.paste(wash, (0, 0), face)
        rim = Image.new("L", image.size)
        ImageDraw.Draw(rim).rounded_rectangle(
            bounds, radius=inner_radius, outline=255, width=scale)
        sheen = _surface(size, (0, 0, 0, 0))
        shine = ImageDraw.Draw(sheen)
        for vertical in range(image.height):
            ratio = vertical / max(1, image.height - 1)
            edge = mix_color(glaze, refraction or border, ratio)
            color = mix_color(fill, edge, .8 - .35 * ratio)
            shine.line((0, vertical, image.width, vertical), fill=color)
        image.paste(sheen, (0, 0), rim)
    return _finish(image, size), inset


def panel_image(size, *, background, fill, border, shadow, radius=22, border_width=1,
                glaze=None, refraction=None, soft_shadow=False):
    width, height = (max(8, round(value)) for value in size)
    radius = max(0, min(round(radius), (min(width, height) - 13) // 2))
    skin, inset = _panel_skin(background, fill, border, shadow, radius, border_width, glaze, refraction, soft_shadow)
    if min(width, height) < skin.width:
        return skin.resize((width, height), Image.Resampling.LANCZOS)
    output = Image.new("RGBA", (width, height), background)
    source = (0, inset, inset + 1, skin.width)
    horizontal = (0, inset, width - inset, width)
    vertical = (0, inset, height - inset, height)
    for row in range(3):
        for column in range(3):
            tile = skin.crop((source[column], source[row], source[column + 1], source[row + 1]))
            target = (horizontal[column + 1] - horizontal[column], vertical[row + 1] - vertical[row])
            if target[0] and target[1]:
                output.paste(tile.resize(target, Image.Resampling.NEAREST), (horizontal[column], vertical[row]))
    return output


def panel_strips(size, **options):
    width, height = (max(8, round(value)) for value in size)
    radius = max(0, min(round(options.get("radius", 22)), (min(width, height) - 13) // 2))
    inset = radius + 6
    if min(width, height) < inset * 2 + 1:
        return [(0, 0, panel_image((width, height), **options))]
    horizontal = panel_image((width, inset * 2 + 1), **options)
    vertical = panel_image((inset * 2 + 1, height), **options)
    return [
        (0, 0, horizontal.crop((0, 0, width, inset))),
        (0, height - inset, horizontal.crop((0, inset + 1, width, inset * 2 + 1))),
        (0, inset, vertical.crop((0, inset, inset, height - inset))),
        (width - inset, inset, vertical.crop((inset + 1, inset, inset * 2 + 1, height - inset))),
    ]


@lru_cache(maxsize=192)
def icon_image(name, size, color):
    image = _surface((size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    unit = size * SUPERSAMPLE / 24
    stroke = max(1, round(1.8 * unit))

    def line(points):
        coords = [(horizontal * unit, vertical * unit) for horizontal, vertical in points]
        draw.line(coords, fill=color, width=stroke, joint="curve")
        for horizontal, vertical in coords:
            radius = stroke / 2
            draw.ellipse((horizontal - radius, vertical - radius, horizontal + radius, vertical + radius), fill=color)

    def curve(start, segments):
        points = [start]
        for first, second, end in segments:
            for step in range(1, 17):
                ratio = step / 16
                inverse = 1 - ratio
                points.append(tuple(inverse ** 3 * start[axis] + 3 * inverse ** 2 * ratio * first[axis]
                                    + 3 * inverse * ratio ** 2 * second[axis] + ratio ** 3 * end[axis]
                                    for axis in (0, 1)))
            start = end
        line(points)

    if name == "home":
        line([(3, 11), (12, 3), (21, 11)])
        line([(6, 10), (6, 21), (18, 21), (18, 10)])
        line([(10, 21), (10, 15), (14, 15), (14, 21)])
    elif name == "book":
        line([(12, 5), (7, 3), (3, 4), (3, 20), (7, 19), (12, 21), (17, 19), (21, 20), (21, 4), (17, 3), (12, 5), (12, 21)])
    elif name == "heart":
        curve((12, 20), [((8, 17), (2, 12), (3, 8)), ((4, 2), (9, 2), (12, 7)),
                         ((15, 2), (20, 2), (21, 8)), ((22, 12), (16, 17), (12, 20))])
    elif name == "leaf":
        curve((5, 20), [((2, 8), (12, 3), (21, 3)), ((21, 15), (17, 23), (5, 20))])
        line([(4, 22), (15, 10)])
    elif name == "settings":
        for vertical, horizontal in ((5, 8), (12, 16), (19, 10)):
            line([(3, vertical), (21, vertical)])
            draw.ellipse(((horizontal - 2) * unit, (vertical - 2) * unit,
                          (horizontal + 2) * unit, (vertical + 2) * unit), fill=color)
    elif name == "photo":
        line([(3, 4), (21, 4), (21, 20), (3, 20), (3, 4)])
        line([(4, 18), (9, 12), (13, 16), (17, 11), (21, 16)])
        draw.ellipse((6 * unit, 7 * unit, 9 * unit, 10 * unit), fill=color)
    elif name == "send":
        line([(3, 4), (22, 12), (3, 20), (7, 12), (3, 4)])
        line([(7, 12), (22, 12)])
    elif name == "moon":
        curve((16, 3), [((2, 1), (0, 19), (12, 21)), ((16, 22), (20, 19), (21, 15)),
                         ((12, 21), (6, 9), (16, 3))])
    elif name == "check":
        line([(5, 12), (10, 17), (20, 6)])
    elif name == "chevron_down":
        line([(6, 9), (12, 15), (18, 9)])
    elif name == "search":
        draw.ellipse((4 * unit, 3 * unit, 17 * unit, 16 * unit), outline=color, width=stroke)
        line([(15, 15), (21, 21)])
    else:
        line([(5, 12), (19, 12)])
        line([(12, 5), (12, 19)])
    return _finish(image, (size, size))


def meter_image(size, energy, background, track, fill):
    image = _surface(size, background)
    draw = ImageDraw.Draw(image)
    scale = SUPERSAMPLE
    width, height = size
    top = (height / 2 - 4) * scale
    bottom = (height / 2 + 4) * scale
    draw.rounded_rectangle((4 * scale, top, (width - 4) * scale, bottom), radius=4 * scale, fill=track)
    amount = max(0, min(1, energy)) * (width - 8)
    if amount > 0:
        draw.rounded_rectangle((4 * scale, top, (4 + amount) * scale, bottom),
                               radius=min(4, amount / 2) * scale, fill=fill)
    return _finish(image, size)


def scrollbar_thumb_image(size, color, *, active=False):
    image = _surface(size, (0, 0, 0, 0))
    if color is not None:
        width, height = size
        thickness = max(3, round(width * (.42 if active else .28)))
        inset = (width - thickness) / 2
        scale = SUPERSAMPLE
        ImageDraw.Draw(image).rounded_rectangle(
            (inset * scale, 2 * scale, (width - inset) * scale, (height - 2) * scale),
            radius=thickness * scale / 2, fill=color,
        )
    return _finish(image, size)


def stage_image(size, colors, *, background=None):
    width, height = size
    background = background or colors.color("stage")
    ambient_size = max(16, width // 3), max(16, height // 3)
    ambient = Image.new("RGB", ambient_size, background)
    ambient_width, ambient_height = ambient_size
    draw = ImageDraw.Draw(ambient)
    draw.ellipse((ambient_width * .16, ambient_height * .12, ambient_width * .84, ambient_height * .82),
                 fill=mix_color(background, colors.color("stage"), .7))
    draw.ellipse((ambient_width * .38, ambient_height * .2, ambient_width * .78, ambient_height * .66),
                 fill=mix_color(background, colors.color("peach"), .4))
    image = ambient.filter(ImageFilter.GaussianBlur(max(2, min(ambient_size) * .07))).resize(size, Image.Resampling.LANCZOS).convert("RGBA")
    floor = _surface(size, (0, 0, 0, 0))
    scale = SUPERSAMPLE
    ImageDraw.Draw(floor).ellipse((width * .22 * scale, height * .87 * scale, width * .78 * scale, height * .94 * scale),
                                  fill=mix_color(background, colors.color("stage_floor"), .45))
    image.alpha_composite(_finish(floor, size))
    return image


def switch_image(size, colors, selected):
    width, height = size
    image = _surface(size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    scale = SUPERSAMPLE
    draw.rounded_rectangle((scale, scale, (width - 1) * scale, (height - 1) * scale),
                           radius=height * scale / 2, fill=colors.color("primary" if selected else "muted"))
    diameter = height - 8
    left = width - diameter - 4 if selected else 4
    draw.ellipse((left * scale, 4 * scale, (left + diameter) * scale, (height - 4) * scale),
                 fill=colors.color("on_primary") if selected else colors.color("surface"))
    if selected:
        draw.line((5 * scale, height * .5 * scale, 8 * scale, height * .65 * scale,
                   13 * scale, height * .35 * scale), fill=colors.color("on_primary"), width=2 * scale)
    return _finish(image, size)


def theme_preview_image(size, colors):
    width, height = size
    image = _surface(size, colors.color("background"))
    draw = ImageDraw.Draw(image)
    scale = SUPERSAMPLE
    inset = min(8, width * .08)
    top = min(4, height * .08)
    for bounds, fill in (
        ((inset, top, width * .32, height * .65), "stage"),
        ((width * .4, top, width - inset, height * .32), "surface"),
        ((width * .55, height * .4, width - inset, height * .65), "soft"),
        ((width * .18, height * .76, width * .82, height - min(2, height * .04)), "navigation"),
    ):
        draw.rounded_rectangle(tuple(value * scale for value in bounds), radius=8 * scale, fill=colors.color(fill))
    return _finish(image, size)


def fit_character(frame, width, height):
    ratio = min(1.5, max(1, width - 20) / frame.width, max(1, height * .84) / frame.height)
    size = (max(1, round(frame.width * ratio)), max(1, round(frame.height * ratio)))
    return frame.resize(size, Image.Resampling.LANCZOS)
