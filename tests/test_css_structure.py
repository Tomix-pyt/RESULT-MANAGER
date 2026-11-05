"""Keeps the CSS tidy: one base.css + one file per page, page rules scoped to their page."""
import glob, os, re
import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
TEMPLATES = os.path.join(ROOT, "app", "templates")
PAGE_CSS = os.path.join(ROOT, "app", "static", "css", "pages")


def page_templates():
    out = {}
    for f in glob.glob(os.path.join(TEMPLATES, "**", "*.html"), recursive=True):
        t = open(f, encoding="utf-8").read()
        m = re.search(r'\{% set page = "([\w-]+)" %\}', t)
        rel = os.path.relpath(f, TEMPLATES)
        if rel not in ("base.html", "macros.html"):
            out[rel] = m.group(1) if m else None
    return out


def test_every_page_template_declares_its_page_and_has_a_css_file():
    for rel, page in page_templates().items():
        assert page, f"{rel} is missing  {{% set page = \"...\" %}}"
        assert os.path.exists(os.path.join(PAGE_CSS, page + ".css")), f"missing css/pages/{page}.css for {rel}"


def test_no_orphan_page_css_files():
    used = set(page_templates().values())
    for f in glob.glob(os.path.join(PAGE_CSS, "*.css")):
        assert os.path.basename(f)[:-4] in used, f"{os.path.basename(f)} is not used by any template"


def test_page_css_is_scoped_to_its_own_page():
    """A rule in pages/foo.css must start with .page-foo so it cannot leak onto other pages."""
    for f in glob.glob(os.path.join(PAGE_CSS, "*.css")):
        name = os.path.basename(f)[:-4]
        css = re.sub(r"/\*.*?\*/", "", open(f, encoding="utf-8").read(), flags=re.S)
        for selectors in re.findall(r"([^{}]+)\{[^{}]*\}", css):
            for s in selectors.split(","):
                if s.strip().startswith(("@page", "@media")):      # paper size / print switches cannot be scoped
                    continue
                assert s.strip().startswith(f".page-{name}"), f"pages/{name}.css has an unscoped selector: {s.strip()}"


def test_no_inline_styles_or_style_tags_in_templates():
    for f in glob.glob(os.path.join(TEMPLATES, "**", "*.html"), recursive=True):
        t = open(f, encoding="utf-8").read()
        assert 'style="' not in t and "<style" not in t, f"inline CSS in {os.path.relpath(f, TEMPLATES)}"


def test_rendered_pages_load_base_and_their_page_css(client, world):
    client.post("/login", data={"username": "admin", "password": "password123"})
    for url, page in [("/admin/", "dashboard"), ("/admin/sessions", "sessions"), ("/admin/classes", "classes"),
                      ("/admin/class-sessions/1", "class-detail"), ("/admin/subjects", "subjects"),
                      ("/admin/students", "students"), ("/admin/students/1", "student-detail"),
                      ("/admin/grading", "grading"), ("/admin/class-subjects/1/assessments", "assessments"),
                      ("/admin/enrollment", "enrollment"), ("/admin/users", "users"),
                      ("/admin/audit", "audit"), ("/admin/settings", "settings")]:
        html = client.get(url).get_data(as_text=True)
        assert "css/base.css" in html, url
        assert f"css/pages/{page}.css" in html, url
        assert f"page-{page}" in html, url
        assert html.count("css/pages/") == 1, f"{url} should load exactly one page stylesheet"
        assert client.get(f"/static/css/pages/{page}.css").status_code == 200
    assert client.get("/static/css/base.css").status_code == 200
