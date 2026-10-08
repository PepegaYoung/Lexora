from dataclasses import dataclass
import re
import time


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float

    def contains(self, x, y):
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h

    def json(self):
        return [self.x, self.y, self.w, self.h]


@dataclass(frozen=True)
class Word:
    text: str
    box: Box


@dataclass(frozen=True)
class Line:
    text: str
    box: Box
    words: tuple[Word, ...]


def normalized(text):
    # Preserve punctuation and digits: do not conflate different game choices.
    return re.sub(r'\s+', ' ', text).strip().casefold()


class Stability:
    """A changing camera is irrelevant: debounce recognized text, not the frame."""
    def __init__(self, delay=.3):
        self.delay = delay
        self.pending = None
        self.changed_at = 0
        self.current = ''

    def observe(self, text, now=None):
        now = time.monotonic() if now is None else now
        key = normalized(text)
        if key != self.pending:
            self.pending, self.changed_at = key, now
        if key != self.current and now - self.changed_at >= self.delay:
            self.current = key
            return True
        return False


class Generation:
    """Reject asynchronous results belonging to an obsolete subtitle or backend."""
    def __init__(self):
        self.value = 0

    def next(self):
        self.value += 1
        return self.value

    def accepts(self, value):
        return value == self.value


def selected_text(lines, selection):
    words = [w.text for line in lines for w in line.words
             if selection.contains(w.box.x + w.box.w / 2, w.box.y + w.box.h / 2)]
    return ' '.join(words)


def map_selection(rect, image_width, image_height, widget_width, widget_height):
    x, y, w, h = rect
    sx, sy = image_width / widget_width, image_height / widget_height
    left = max(0, min(image_width, round(x * sx)))
    top = max(0, min(image_height, round(y * sy)))
    right = max(left, min(image_width, round((x + w) * sx)))
    bottom = max(top, min(image_height, round((y + h) * sy)))
    return Box(left, top, right - left, bottom - top)
