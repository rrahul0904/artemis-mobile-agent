from __future__ import annotations
import re
import xml.etree.ElementTree as ET
from .models import UIElement

_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")

def parse_elements(xml: str) -> list[UIElement]:
    if not xml.strip():
        return []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    out: list[UIElement] = []
    for node in root.iter():
        m = _BOUNDS.fullmatch(node.attrib.get("bounds", ""))
        if not m:
            continue
        bounds = tuple(map(int, m.groups()))
        if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            continue
        text = node.attrib.get("text", "")
        desc = node.attrib.get("content-desc", "")
        rid = node.attrib.get("resource-id", "")
        cls = node.attrib.get("class", "")
        if not (text or desc or rid or node.attrib.get("clickable") == "true"):
            continue
        out.append(UIElement(index=len(out), text=text, content_desc=desc, resource_id=rid, class_name=cls, bounds=bounds))
    return out

def normalized(center: tuple[int, int], width: int, height: int) -> tuple[int, int]:
    x, y = center
    return (max(0, min(1000, round(x * 1000 / max(width, 1)))), max(0, min(1000, round(y * 1000 / max(height, 1)))))

def denormalized(target: tuple[int, int], width: int, height: int) -> tuple[int, int]:
    x, y = target
    return (round(x * width / 1000), round(y * height / 1000))
