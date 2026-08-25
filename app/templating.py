import os

from fastapi.templating import Jinja2Templates

from app.scoring import SOURCE_LABELS

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

_PILL_CLASSES = {
    "AI Category Leader": "leader",
    "Sterke AI-positie": "strong",
    "Op de goede weg": "ok",
    "Kwetsbaar": "weak",
    "Onzichtbaar": "invisible",
}


def classification_pill_class(label: str) -> str:
    return _PILL_CLASSES.get(label, "invisible")


def source_label(source: str) -> str:
    value = source.value if hasattr(source, "value") else source
    return SOURCE_LABELS.get(value, value)


templates.env.filters["pill_class"] = classification_pill_class
templates.env.filters["source_label"] = source_label
