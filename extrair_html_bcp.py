from __future__ import annotations

import argparse
import difflib
import hashlib
import html
import json
import logging
import os
import re
import sys
import unicodedata
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse


URL = "https://www.bcp.gov.py/web/institucional/circulares"
DEFAULT_KEEP_RUNS = 10
TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S_%f"


@dataclass
class Circular:
    id: str
    title: str
    number: str
    year: str
    month: str
    category: str
    url: str

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "title": self.title,
            "number": self.number,
            "year": self.year,
            "month": self.month,
            "category": self.category,
            "url": self.url,
        }

class CircularListParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.items: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None
        self._div_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name.lower(): value or "" for name, value in attrs}
        css_class = attr.get("class", "")

        if (
            self._current is None
            and tag.lower() == "div"
            and "list__item" in css_class
            and "search-item" in css_class
        ):
            self._current = {"attrs": attr, "texts": [], "links": []}
            self._div_depth = 1
            return

        if self._current is None:
            return

        if tag.lower() == "div":
            self._div_depth += 1
        elif tag.lower() == "a" and attr.get("href"):
            attr["href"] = urljoin(self.base_url, attr["href"])
            self._current["links"].append(attr)

    def handle_endtag(self, tag: str) -> None:
        if self._current is None or tag.lower() != "div":
            return

        self._div_depth -= 1
        if self._div_depth <= 0:
            self.items.append(self._current)
            self._current = None
            self._div_depth = 0

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return

        text = normalize_spaces(data)
        if text:
            self._current["texts"].append(text)


class VisibleTextParser(HTMLParser):
    SKIP_TAGS = {"script", "style", "svg", "noscript", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return

        text = normalize_spaces(data)
        if text:
            self.lines.append(text)


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.casefold()
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def canonical_url(value: str) -> str:
    if not value:
        return ""

    without_fragment, _fragment = urldefrag(value)
    parsed = urlparse(without_fragment)
    return parsed._replace(query="").geturl()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def extract_number(title: str) -> str:
    match = re.search(r"\bCIRCULAR\b.*?\bN\S*\s*([0-9]+/[0-9]{4})", title, re.IGNORECASE)
    return match.group(1) if match else ""


def clean_item_title(texts: list[str]) -> str:
    ignored = {"download", "descargar", "visibility", "vista previa"}
    useful = [part for part in texts if normalize_key(part) not in ignored]
    return normalize_spaces(" ".join(useful))


def build_circular_id(title: str, number: str, url: str) -> str:
    if number:
        identity = f"{number}|{normalize_key(title)}"
    elif url:
        identity = canonical_url(url)
    else:
        identity = normalize_key(title)

    return sha256_text(identity)[:16]


def choose_document_url(links: list[dict[str, str]]) -> str:
    if not links:
        return ""

    for link in links:
        href = link.get("href", "")
        if "download" in link or "download" in normalize_key(link.get("class", "")):
            return href

    for link in links:
        href = link.get("href", "")
        if "/documents/" in href:
            return href

    return links[0].get("href", "")


def extract_circulars(page_html: str, base_url: str) -> list[Circular]:
    parser = CircularListParser(base_url)
    parser.feed(page_html)

    circulars: list[Circular] = []
    seen: set[str] = set()

    for item in parser.items:
        title = clean_item_title(item["texts"])
        if not title or "circular" not in normalize_key(title):
            continue

        url = choose_document_url(item["links"])
        attrs = item["attrs"]
        number = extract_number(title)
        circular_id = build_circular_id(title, number, url)

        if circular_id in seen:
            continue

        seen.add(circular_id)
        circulars.append(
            Circular(
                id=circular_id,
                title=title,
                number=number,
                year=attrs.get("data-value", ""),
                month=attrs.get("data-mes", ""),
                category=attrs.get("data-categoria", ""),
                url=url,
            )
        )

    return circulars


def extract_visible_lines(page_html: str) -> list[str]:
    parser = VisibleTextParser()
    parser.feed(page_html)

    lines: list[str] = []
    previous = ""
    for line in parser.lines:
        if line != previous:
            lines.append(line)
        previous = line

    return lines


def get_user_base_dir() -> Path:
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Bot BCP"


def ensure_directories(base_dir: Path) -> dict[str, Path]:
    dirs = {
        "base": base_dir,
        "html": base_dir / "html",
        "snapshots": base_dir / "snapshots",
        "text": base_dir / "text",
        "reports": base_dir / "reports",
        "logs": base_dir / "logs",
    }

    for folder in dirs.values():
        folder.mkdir(parents=True, exist_ok=True)

    return dirs


def configure_logging(log_dir: Path) -> None:
    log_file = log_dir / "bot.log"
    handlers: list[logging.Handler] = [logging.FileHandler(log_file, encoding="utf-8")]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
        force=True,
    )


def console_print(message: str) -> None:
    if sys.stdout is not None:
        print(message)


def is_cloudflare_challenge(page_html: str) -> bool:
    lowered = page_html.casefold()
    return (
        "challenges.cloudflare.com" in lowered
        or "cf_chl" in lowered
        or "verificación de seguridad" in lowered
        or "verificacao de seguranca" in lowered
    )


def minimize_browser_window(page: Any) -> None:
    try:
        session = page.context.new_cdp_session(page)
        window_info = session.send("Browser.getWindowForTarget")
        session.send(
            "Browser.setWindowBounds",
            {
                "windowId": window_info["windowId"],
                "bounds": {"windowState": "minimized"},
            },
        )
    except Exception as exc:
        logging.warning("Nao consegui minimizar a janela do navegador: %s", exc)


def fetch_live_html(
    url: str,
    timeout_ms: int,
    headless: bool,
    minimized: bool,
    user_data_dir: Path,
) -> str:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright nao esta instalado. Rode: "
            "python -m pip install -r requirements.txt "
            "e depois python -m playwright install chromium"
        ) from exc

    logging.info("Acessando %s", url)
    launch_args = []
    if minimized and not headless:
        launch_args = [
            "--start-minimized",
            "--window-position=-32000,-32000",
            "--window-size=800,600",
        ]

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            headless=headless,
            locale="es-PY",
            args=launch_args,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            if minimized and not headless:
                minimize_browser_window(page)

            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                logging.warning("networkidle nao ocorreu; seguindo com o HTML carregado.")

            try:
                selector_timeout = 180000 if not headless else 20000
                page.wait_for_selector("div.list__item.search-item", timeout=selector_timeout)
            except PlaywrightTimeoutError:
                logging.warning("Nao encontrei div.list__item.search-item dentro do tempo limite.")

            logging.info("HTML da pagina de circulares capturado.")
            return page.content()
        finally:
            context.close()


def read_html_source(
    source_html: str | None,
    url: str,
    timeout_ms: int,
    headless: bool,
    minimized: bool,
    user_data_dir: Path,
) -> tuple[str, str]:
    if source_html:
        path = Path(source_html).expanduser().resolve()
        logging.info("Lendo HTML local: %s", path)
        return path.read_text(encoding="utf-8", errors="ignore"), str(path)

    return fetch_live_html(url, timeout_ms, headless, minimized, user_data_dir), url


def save_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_previous_snapshot(snapshot_dir: Path, current_snapshot: Path) -> Path | None:
    snapshots = sorted(
        [path for path in snapshot_dir.glob("*.json") if path != current_snapshot],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return snapshots[0] if snapshots else None


def load_snapshot_text(snapshot: dict[str, Any]) -> list[str]:
    text_file = snapshot.get("text_file")
    if not text_file:
        return []

    path = Path(text_file)
    if not path.exists():
        return []

    return path.read_text(encoding="utf-8", errors="ignore").splitlines()


def compare_snapshots(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
    previous_lines: list[str],
    current_lines: list[str],
) -> dict[str, Any]:
    if previous is None:
        return {
            "status": "primeira_execucao",
            "page_changed": True,
            "new_items": [],
            "removed_items": [],
            "changed_items": [],
            "diff_lines": [],
        }

    previous_circulars = previous.get("circulars", []) if previous else []
    current_circulars = current.get("circulars", [])

    previous_by_id = {item["id"]: item for item in previous_circulars}
    current_by_id = {item["id"]: item for item in current_circulars}

    new_items = [item for item in current_circulars if item["id"] not in previous_by_id]
    removed_items = [item for item in previous_circulars if item["id"] not in current_by_id]
    changed_items = [
        {
            "before": previous_by_id[item_id],
            "after": current_by_id[item_id],
        }
        for item_id in sorted(previous_by_id.keys() & current_by_id.keys())
        if previous_by_id[item_id] != current_by_id[item_id]
    ]

    page_changed = previous is None or previous.get("text_hash") != current.get("text_hash")

    diff_lines: list[str] = []
    if previous is not None:
        diff_lines = list(
            difflib.unified_diff(
                previous_lines,
                current_lines,
                fromfile=Path(previous.get("text_file", "anterior")).name,
                tofile=Path(current.get("text_file", "atual")).name,
                lineterm="",
            )
        )

    if new_items:
        status = "nova_circular"
    elif removed_items or changed_items:
        status = "circulares_alteradas"
    elif page_changed:
        status = "pagina_alterada"
    else:
        status = "sem_mudanca"

    return {
        "status": status,
        "page_changed": page_changed,
        "new_items": new_items,
        "removed_items": removed_items,
        "changed_items": changed_items,
        "diff_lines": diff_lines,
    }


def status_label(status: str) -> str:
    labels = {
        "primeira_execucao": "Primeira execucao",
        "nova_circular": "Nova circular encontrada",
        "circulares_alteradas": "Circulares alteradas",
        "pagina_alterada": "Pagina alterada sem nova circular",
        "sem_mudanca": "Sem mudanca",
        "erro": "Erro na execucao",
    }
    return labels.get(status, status)


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def file_link(path: str | Path, label: str | None = None) -> str:
    resolved = Path(path).resolve()
    text = label or resolved.name
    return f'<a href="{resolved.as_uri()}">{escape(text)}</a>'


def external_link(url: str, label: str | None = None) -> str:
    if not url:
        return ""
    text = label or url
    return f'<a href="{escape(url)}" target="_blank" rel="noopener">{escape(text)}</a>'


def render_circular_table(title: str, items: list[dict[str, Any]], highlight: bool = False) -> str:
    if not items:
        return f"<section><h2>{escape(title)}</h2><p>Nenhum item.</p></section>"

    rows = []
    row_class = ' class="changed-row"' if highlight else ""
    for item in items:
        rows.append(
            f"<tr{row_class}>"
            f"<td>{escape(item.get('number', ''))}</td>"
            f"<td>{escape(item.get('year', ''))}</td>"
            f"<td>{escape(item.get('month', ''))}</td>"
            f"<td>{escape(item.get('title', ''))}</td>"
            f"<td>{external_link(item.get('url', ''), 'Abrir')}</td>"
            "</tr>"
        )

    return (
        f"<section><h2>{escape(title)}</h2>"
        "<table><thead><tr>"
        "<th>Numero</th><th>Ano</th><th>Mes</th><th>Titulo</th><th>Link</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></section>"
    )


def render_changed_table(changed_items: list[dict[str, dict[str, Any]]]) -> str:
    if not changed_items:
        return "<section><h2>Circulares com dados alterados</h2><p>Nenhum item.</p></section>"

    rows = []
    for item in changed_items:
        before = item["before"]
        after = item["after"]
        rows.append(
            '<tr class="changed-row">'
            f"<td>{escape(after.get('number', before.get('number', '')))}</td>"
            f"<td>{escape(before.get('title', ''))}</td>"
            f"<td>{escape(after.get('title', ''))}</td>"
            f"<td>{external_link(before.get('url', ''), 'Antes')}<br>{external_link(after.get('url', ''), 'Depois')}</td>"
            "</tr>"
        )

    return (
        "<section><h2>Circulares com dados alterados</h2>"
        "<table><thead><tr>"
        "<th>Numero</th><th>Antes</th><th>Depois</th><th>Links</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></section>"
    )


def render_diff(diff_lines: list[str]) -> str:
    if not diff_lines:
        return "<section><h2>Diff do texto limpo</h2><p>Nenhuma diferenca textual encontrada.</p></section>"

    rendered = []
    for line in diff_lines:
        css_class = ""
        if line.startswith("+") and not line.startswith("+++"):
            css_class = "changed-line add"
        elif line.startswith("-") and not line.startswith("---"):
            css_class = "changed-line remove"
        elif line.startswith("@@"):
            css_class = "meta"

        rendered.append(f'<span class="{css_class}">{escape(line)}</span>')

    return "<section><h2>Diff do texto limpo</h2><pre>" + "\n".join(rendered) + "</pre></section>"


def write_report(
    report_path: Path,
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    comparison: dict[str, Any],
) -> None:
    status = comparison["status"]
    generated_at = current["timestamp"]
    has_changes = bool(
        comparison["new_items"]
        or comparison["removed_items"]
        or comparison["changed_items"]
        or status == "pagina_alterada"
    )
    status_class = "status status-changed" if has_changes else "status"
    new_summary_class = "summary-item summary-changed" if comparison["new_items"] else "summary-item"
    removed_summary_class = "summary-item summary-changed" if comparison["removed_items"] else "summary-item"
    changed_summary_class = "summary-item summary-changed" if comparison["changed_items"] else "summary-item"

    previous_info = "Nenhum snapshot anterior."
    if previous is not None:
        previous_info = (
            f"Comparado com {escape(previous.get('timestamp', 'snapshot anterior'))} "
            f"({file_link(previous.get('snapshot_file', ''), 'snapshot anterior')})."
        )

    html_content = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Bot BCP - {escape(status_label(status))}</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Arial, Helvetica, sans-serif;
      color: #1f2933;
      background: #f5f7fa;
    }}
    body {{
      margin: 0;
      padding: 32px;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      background: #ffffff;
      border: 1px solid #d8dee6;
      border-radius: 8px;
      padding: 28px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
    }}
    h2 {{
      border-bottom: 1px solid #e5e9f0;
      font-size: 18px;
      margin-top: 28px;
      padding-bottom: 8px;
    }}
    .status {{
      display: inline-block;
      border-radius: 999px;
      padding: 6px 12px;
      background: #e8f2ff;
      color: #174a7c;
      font-weight: 700;
      margin-bottom: 18px;
    }}
    .status-changed {{
      background: #fde8e8;
      color: #b42318;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin: 20px 0;
    }}
    .summary-item {{
      border: 1px solid #e5e9f0;
      border-radius: 6px;
      padding: 12px;
      background: #fbfcfd;
    }}
    .summary-changed {{
      border-color: #f6b4b4;
      background: #fde8e8;
      color: #b42318;
    }}
    .summary strong {{
      display: block;
      font-size: 22px;
      margin-bottom: 4px;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      table-layout: fixed;
    }}
    th, td {{
      border: 1px solid #d8dee6;
      padding: 8px;
      text-align: left;
      vertical-align: top;
      word-wrap: break-word;
    }}
    th {{
      background: #eef2f7;
    }}
    .changed-row td {{
      background: #fde8e8;
      color: #b42318;
      font-weight: 600;
    }}
    .changed-row a {{
      color: #991b1b;
      font-weight: 700;
    }}
    pre {{
      overflow: auto;
      white-space: pre-wrap;
      border: 1px solid #d8dee6;
      border-radius: 6px;
      background: #111827;
      color: #e5e7eb;
      padding: 16px;
      line-height: 1.45;
      max-height: 720px;
    }}
    pre span {{
      display: block;
      padding: 1px 4px;
    }}
    pre .changed-line {{
      background: #fde8e8;
      color: #b42318;
      font-weight: 700;
    }}
    pre .meta {{
      color: #93c5fd;
    }}
    a {{
      color: #0f5ea8;
    }}
    @media print {{
      body {{
        background: #fff;
        padding: 0;
      }}
      main {{
        border: none;
      }}
      pre {{
        max-height: none;
      }}
    }}
  </style>
</head>
<body>
<main>
  <h1>Bot BCP - Monitor de Circulares</h1>
  <div class="{status_class}">{escape(status_label(status))}</div>
  <p>Execucao: {escape(generated_at)}</p>
  <p>{previous_info}</p>
  <p>Fonte: {escape(current.get('source', ''))}</p>
  <p>Arquivos: {file_link(current['html_file'], 'HTML bruto')} | {file_link(current['text_file'], 'texto limpo')} | {file_link(current['snapshot_file'], 'snapshot JSON')}</p>

  <section class="summary">
    <div class="{new_summary_class}"><strong>{len(comparison['new_items'])}</strong>Novas circulares</div>
    <div class="{removed_summary_class}"><strong>{len(comparison['removed_items'])}</strong>Circulares removidas</div>
    <div class="{changed_summary_class}"><strong>{len(comparison['changed_items'])}</strong>Circulares alteradas</div>
    <div class="summary-item"><strong>{len(current['circulars'])}</strong>Total atual</div>
  </section>

  {render_circular_table('Novas circulares', comparison['new_items'], highlight=True)}
  {render_circular_table('Circulares removidas', comparison['removed_items'], highlight=True)}
  {render_changed_table(comparison['changed_items'])}
  {render_circular_table('Todas as circulares detectadas agora', current['circulars'])}
  {render_diff(comparison['diff_lines'])}
</main>
</body>
</html>
"""
    save_text(report_path, html_content)


def write_error_report(report_path: Path, error: Exception, timestamp: str, source: str) -> None:
    html_content = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Bot BCP - Erro</title>
  <style>
    body {{ font-family: Arial, Helvetica, sans-serif; margin: 32px; color: #1f2933; }}
    main {{ max-width: 900px; margin: 0 auto; border: 1px solid #d8dee6; border-radius: 8px; padding: 24px; }}
    pre {{ white-space: pre-wrap; background: #111827; color: #fca5a5; padding: 16px; border-radius: 6px; }}
  </style>
</head>
<body>
<main>
  <h1>Bot BCP - Erro na execucao</h1>
  <p>Execucao: {escape(timestamp)}</p>
  <p>Fonte: {escape(source)}</p>
  <pre>{escape(repr(error))}</pre>
</main>
</body>
</html>
"""
    save_text(report_path, html_content)


def generate_pdf(report_path: Path, pdf_path: Path) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logging.warning("PDF nao gerado: Playwright nao esta instalado.")
        return False

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(report_path.resolve().as_uri(), wait_until="load")
            page.pdf(path=str(pdf_path), format="A4", print_background=True)
            return True
        finally:
            browser.close()


def cleanup_old_runs(base_dir: Path, keep_runs: int) -> None:
    if keep_runs < 1:
        keep_runs = 1

    managed_dirs = ["html", "snapshots", "text", "reports"]
    files_by_run: dict[str, list[Path]] = {}
    newest_mtime_by_run: dict[str, float] = {}

    for name in managed_dirs:
        folder = base_dir / name
        if not folder.exists():
            continue

        for path in folder.iterdir():
            if not path.is_file():
                continue

            run_id = path.stem
            files_by_run.setdefault(run_id, []).append(path)
            newest_mtime_by_run[run_id] = max(
                newest_mtime_by_run.get(run_id, 0),
                path.stat().st_mtime,
            )

    keep_ids = {
        run_id
        for run_id, _mtime in sorted(
            newest_mtime_by_run.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:keep_runs]
    }

    for run_id, paths in files_by_run.items():
        if run_id in keep_ids:
            continue

        for path in paths:
            logging.info("Removendo arquivo antigo: %s", path)
            path.unlink()


def run_monitor(args: argparse.Namespace) -> Path:
    base_dir = Path(args.base_dir).expanduser().resolve() if args.base_dir else get_user_base_dir()
    dirs = ensure_directories(base_dir)
    configure_logging(dirs["logs"])
    browser_profile_dir = (
        Path(args.user_data_dir).expanduser().resolve()
        if args.user_data_dir
        else base_dir / "browser_profile"
    )
    browser_profile_dir.mkdir(parents=True, exist_ok=True)

    timestamp_dt = datetime.now()
    timestamp = timestamp_dt.strftime(TIMESTAMP_FORMAT)

    html_path = dirs["html"] / f"{timestamp}.html"
    text_path = dirs["text"] / f"{timestamp}.txt"
    snapshot_path = dirs["snapshots"] / f"{timestamp}.json"
    report_path = dirs["reports"] / f"{timestamp}.html"
    pdf_path = dirs["reports"] / f"{timestamp}.pdf"

    logging.info("Base de dados: %s", base_dir)
    page_html, source = read_html_source(
        args.source_html,
        args.url,
        args.timeout_ms,
        headless=args.headless,
        minimized=args.minimized,
        user_data_dir=browser_profile_dir,
    )
    save_text(html_path, page_html)

    visible_lines = extract_visible_lines(page_html)
    clean_text = "\n".join(visible_lines)
    save_text(text_path, clean_text)

    if is_cloudflare_challenge(page_html):
        raise RuntimeError(
            "O site do BCP entregou uma verificacao do Cloudflare em vez da lista de circulares. "
            "Rode no modo padrao com navegador visivel para resolver a verificacao; "
            f"o perfil sera reaproveitado em {browser_profile_dir}."
        )

    circulars = extract_circulars(page_html, args.url)
    logging.info("Circulares detectadas: %s", len(circulars))

    if not circulars:
        raise RuntimeError(
            "Nenhuma circular foi detectada na pagina. "
            "O HTML foi salvo para analise, mas o snapshot nao foi atualizado."
        )

    current_snapshot = {
        "timestamp": timestamp_dt.isoformat(timespec="seconds"),
        "url": args.url,
        "source": source,
        "html_file": str(html_path),
        "text_file": str(text_path),
        "snapshot_file": str(snapshot_path),
        "html_hash": sha256_text(page_html),
        "text_hash": sha256_text(clean_text),
        "circular_count": len(circulars),
        "circulars": [item.as_dict() for item in circulars],
    }
    save_json(snapshot_path, current_snapshot)

    previous_snapshot_path = latest_previous_snapshot(dirs["snapshots"], snapshot_path)
    previous_snapshot = load_json(previous_snapshot_path) if previous_snapshot_path else None
    previous_lines = load_snapshot_text(previous_snapshot) if previous_snapshot else []

    comparison = compare_snapshots(previous_snapshot, current_snapshot, previous_lines, visible_lines)
    logging.info("Status: %s", comparison["status"])

    write_report(report_path, current_snapshot, previous_snapshot, comparison)

    if not args.no_pdf:
        if generate_pdf(report_path, pdf_path):
            logging.info("PDF gerado: %s", pdf_path)

    cleanup_old_runs(base_dir, args.keep_runs)

    if not args.no_open:
        webbrowser.open(report_path.resolve().as_uri())

    return report_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitora novas circulares no site do BCP.")
    parser.add_argument("--url", default=URL, help="URL da pagina de circulares.")
    parser.add_argument("--base-dir", help="Pasta onde o historico sera salvo. Padrao: %%USERPROFILE%%\\Bot BCP.")
    parser.add_argument("--source-html", help="HTML local para teste, sem acessar a internet.")
    parser.add_argument("--keep-runs", type=int, default=DEFAULT_KEEP_RUNS, help="Quantidade de execucoes a manter.")
    parser.add_argument("--timeout-ms", type=int, default=60000, help="Timeout do Playwright em milissegundos.")
    browser_mode = parser.add_mutually_exclusive_group()
    browser_mode.add_argument(
        "--headed",
        dest="headless",
        action="store_false",
        help="Abre o navegador visivel para validacoes do site. Este e o padrao.",
    )
    browser_mode.add_argument(
        "--headless",
        dest="headless",
        action="store_true",
        help="Roda com navegador invisivel. Use apenas se o site nao bloquear.",
    )
    parser.set_defaults(headless=False)
    parser.add_argument(
        "--minimized",
        action="store_true",
        help="Inicia o navegador visivel minimizado. Funciona apenas fora do modo --headless.",
    )
    parser.add_argument("--user-data-dir", help="Perfil persistente do navegador usado pelo Playwright.")
    parser.add_argument("--no-open", action="store_true", help="Nao abrir o relatorio no navegador.")
    parser.add_argument("--no-pdf", action="store_true", help="Nao gerar PDF do relatorio.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    try:
        report_path = run_monitor(args)
        console_print(f"Relatorio gerado: {report_path}")
        return 0
    except Exception as exc:
        base_dir = Path(args.base_dir).expanduser().resolve() if args.base_dir else get_user_base_dir()
        dirs = ensure_directories(base_dir)
        configure_logging(dirs["logs"])

        timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
        report_path = dirs["reports"] / f"{timestamp}_erro.html"
        logging.exception("Falha na execucao")
        write_error_report(report_path, exc, timestamp, args.source_html or args.url)
        cleanup_old_runs(base_dir, args.keep_runs)

        if not args.no_open:
            webbrowser.open(report_path.resolve().as_uri())

        console_print(f"Erro. Relatorio gerado: {report_path}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
