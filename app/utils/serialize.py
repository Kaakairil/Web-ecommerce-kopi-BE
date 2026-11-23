"""Serialization helpers shared by product routes (moved from legacy
ProductController to keep the exact same payload shape)."""
import json
import re


def _parse_specs(raw_specs):
    specs = []
    try:
        if raw_specs is None:
            specs = []
        elif isinstance(raw_specs, (list, tuple)):
            specs = list(raw_specs)
        else:
            s = str(raw_specs).strip()
            try:
                j = json.loads(s)
                if isinstance(j, list):
                    specs = [str(x).strip() for x in j if str(x).strip()]
                else:
                    specs = []
            except Exception:
                parts = re.split(r"\r?\n|<br\s*/?>|;|\|", s)
                specs = [p.strip() for p in parts if p and p.strip()]
    except Exception:
        specs = []
    return specs


def _parse_spec_meta(specs):
    spec_meta = {}
    try:
        for s in specs:
            if not s or ":" not in s:
                continue
            k, v = s.split(":", 1)
            key = k.strip().lower().replace(" ", "_")
            if key:
                spec_meta[key] = v.strip()
    except Exception:
        spec_meta = {}
    return spec_meta


def _serialize(product, stock):
    specs = _parse_specs(product.get("specifications"))
    return {
        "id": product.get("id"),
        "name": product.get("name"),
        "description": product.get("description"),
        "price": float(product.get("price")) if product.get("price") else 0,
        "original_price": float(product.get("original_price")) if product.get("original_price") else None,
        "category": product.get("category"),
        "image_url": product.get("image_url"),
        "is_available": product.get("is_available"),
        "is_featured": product.get("is_featured"),
        "is_discounted": product.get("is_discounted"),
        "discount_percentage": product.get("discount_percentage"),
        "rating": product.get("rating"),
        "stock": stock.get("quantity", 0) if stock else 0,
        "weight": product.get("weight"),
        "type": product.get("type"),
        "origin": product.get("origin"),
        "process": product.get("process"),
        "roast_level": product.get("roast_level"),
        "flavor_notes": product.get("flavor_notes"),
        "brewing_methods": product.get("brewing_methods"),
        "specifications": product.get("specifications"),
        "specs": specs,
        "spec_meta": _parse_spec_meta(specs),
        "grade": product.get("grade"),
        "certification": product.get("certification"),
    }


def transform(products, stock_map=None):
    return [_serialize(p, (stock_map or {}).get(p.get("id"))) for p in products]


def single_transform(product, stock=None):
    data = _serialize(product, stock)
    data["min_stock"] = stock.get("min_stock", 10) if stock else 10
    data["created_at"] = product.get("created_at")
    data["updated_at"] = product.get("updated_at")
    return data
