#!/usr/bin/env python3
"""Replace first-child Computer cover JPEGs with credited public-domain / CC files."""
from __future__ import annotations

import csv
import json
import os
import re
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

RESOURCE = Path(r"H:\Website\site\project\root\Resource\Computer")
CSV_PATH = Path(r"H:\Website\site\project\config\Computer_image_credits.csv")
BACKUP = RESOURCE / "_uncited_backup"
CATEGORIES = ("OS", "Program", "Programming", "Technology")
UA = "UjnotesCoverBot/1.0 (https://ujnotes.com/; cover attribution; python)"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
SIMPLE_ICONS_JSON = "https://cdn.jsdelivr.net/npm/simple-icons@15/data/simple-icons.json"
CTX = ssl.create_default_context()

SEARCH_OVERRIDE = {
    "android": "Android robot logo",
    "cygwin": "Cygwin logo",
    "ios": "Apple logo",
    "mac": "Apple logo macOS",
    "nix": "Tux Linux penguin",
    "windows": "Windows 11 logo",
    "ajax": "AJAX programming logo",
    "awk": "AWK programming language",
    "cpp": "C++ logo",
    "css": "CSS3 logo",
    "ftp": "File Transfer Protocol icon",
    "fusionchart": "FusionCharts logo",
    "google_api": "Google APIs logo",
    "google_cloud_platform_functions": "Google Cloud Functions logo",
    "html": "HTML5 logo",
    "http": "HTTP logo",
    "java": "Java programming language logo",
    "javascript": "JavaScript logo",
    "json": "JSON logo",
    "jsp": "Jakarta Server Pages logo",
    "latex": "LaTeX logo",
    "lines_of_code": "source code editor screenshot free",
    "log4j": "Apache Log4j logo",
    "logitech_lua": "Lua programming language logo",
    "markdown": "Markdown mark",
    "ms_sql": "Microsoft SQL Server logo",
    "nant": "NAnt build tool",
    "php": "PHP logo",
    "powershell": "PowerShell logo",
    "python": "Python logo notext",
    "r": "R programming language logo",
    "regex": "Regular expression icon",
    "servlet": "Jakarta Servlet",
    "spring_boot": "Spring Boot logo",
    "sql": "SQL logo",
    "typescript": "TypeScript logo",
    "vb_script": "VBScript",
    "versioning": "Software versioning Git",
    "visual_cpp": "Visual C++ logo",
    "visual_studio": "Visual Studio logo",
    "winapi": "Windows API",
    "wix": "WiX Toolset logo",
    "xml": "XML logo",
    "algorithms": "algorithm flowchart",
    "cap_theorem": "CAP theorem",
    "digital_certificate": "TLS padlock certificate",
    "email": "email icon",
    "hardware": "computer motherboard",
    "license": "Creative Commons license logo",
    "llm": "artificial neural network",
    "machine_learning": "machine learning",
    "nfc": "NFC logo",
    "proxy": "proxy server",
    "rss": "RSS feed icon",
    "adobe_premier_pro": "Adobe Premiere Pro logo",
    "amazon_cloud_reader": "Amazon Kindle logo",
    "amd_crimson": "AMD Radeon logo",
    "gscript": "Google Apps Script logo",
    "gtalk": "Google Talk logo",
    "google_apps": "Google Workspace logo",
    "google_search": "Google logo",
    "ie": "Internet Explorer logo",
    "internet_explorer": "Internet Explorer logo",
    "origin": "EA Origin logo",
    "sed": "GNU logo",
    "vi": "Vim logo",
    "wol": "Wake-on-LAN",
    "notepad": "Notepad Windows",
    "grub": "GNU GRUB",
}

SIMPLE_SLUG_OVERRIDE = {
    "adobe_illustrator": "adobeillustrator",
    "adobe_premier_pro": "adobepremierepro",
    "amazon_cloud_reader": "amazon",
    "amd_crimson": "amd",
    "android_studio": "androidstudio",
    "apache_httpd": "apache",
    "apache_maven": "apachemaven",
    "apache_tomcat": "apachetomcat",
    "aws": "amazonaws",
    "certbot": "letsencrypt",
    "cvs": "concurrentversionsystem",
    "davinci_resolve": "davinciresolve",
    "dd_wrt": "ddwrt",
    "eclipse": "eclipseide",
    "filezilla_client": "filezilla",
    "free_download_manager": None,
    "google_analytics": "googleanalytics",
    "google_apps": "googleworkspace",
    "google_chrome": "googlechrome",
    "google_cloud": "googlecloud",
    "google_drive": "googledrive",
    "google_maps": "googlemaps",
    "google_search": "google",
    "google_translate": "googletranslate",
    "google_api": "google",
    "google_cloud_platform_functions": "googlecloud",
    "gtalk": "googlehangouts",
    "ie": "internetexplorer",
    "internet_explorer": "internetexplorer",
    "installshield": None,
    "java": None,
    "groovy": "apachegroovy",
    "wget": None,
    "microsoft_excel": "microsoftexcel",
    "microsoft_office": "microsoft365",
    "microsoft_outlook": "microsoftoutlook",
    "microsoft_remote_desktop": "microsoft",
    "microsoft_security_essentials": "windowsdefender",
    "microsoft_sql_server": "microsoftsqlserver",
    "microsoft_visual_studio": "visualstudio",
    "microsoft_word": "microsoftword",
    "ms_sql": "microsoftsqlserver",
    "netbeans": "apachenetbeanside",
    "nextjs": "nextdotjs",
    "nodejs": "nodedotjs",
    "obs_studio": "obsstudio",
    "spring_boot": "springboot",
    "svn": "subversion",
    "vs_code": "visualstudiocode",
    "visual_studio": "visualstudio",
    "visual_cpp": "visualstudio",
    "windows_media_player": "windows",
    "windows_terminal": "windowsterminal",
    "cpp": "cplusplus",
    "css": "css",
    "html": "html5",
    "ios": "ios",
    "mac": "macos",
    "nix": None,
    "windows": "windows",
    "android": "android",
    "angular": "angular",
    "javascript": "javascript",
    "typescript": "typescript",
    "python": "python",
    "php": "php",
    "r": "r",
    "regex": None,
    "markdown": "markdown",
    "latex": "latex",
    "powershell": "powershell",
    "firebase": "firebase",
    "xml": "xml",
    "json": "json",
    "http": None,
    "ftp": None,
    "ajax": None,
    "awk": None,
    "jsp": None,
    "servlet": None,
    "winapi": "windows",
    "wix": None,  # WiX Toolset, not Wix.com
    "versioning": "git",
    "lines_of_code": None,
    "log4j": "apache",
    "logitech_lua": "lua",
    "fusionchart": None,
    "nant": None,
    "cygwin": None,
    "rss": "rss",
    "nfc": "nfc",
    "email": "maildotru",
    "license": "creativecommons",
    "algorithms": None,
    "cap_theorem": None,
    "digital_certificate": "letsencrypt",
    "hardware": None,
    "llm": None,
    "machine_learning": None,
    "proxy": None,
    "grub": "gnu",
    "sed": "gnu",
    "vi": "vim",
    "origin": "ea",
    "wol": None,
    "notepad": "windows",
    "gscript": "google",
    "putty": "putty",
    "wget": None,
    "tesseract": None,
    "utorrent": None,
    "viber": "viber",
    "zbrush": None,
    "maya": "autodesk",
    "mermaid": "mermaid",
    "db2": "ibm",
    "dbeaver": "dbeaver",
    "jmeter": "apache",
    "openssl": "openssl",
    "postgresql": "postgresql",
    "mysql": "mysql",
    "docker": "docker",
    "git": "git",
    "github": "github",
    "blender": "blender",
    "gimp": "gimp",
    "inkscape": "inkscape",
    "unity": "unity",
    "vulkan": "vulkan",
    "steam": "steam",
    "slack": "slack",
    "whatsapp": "whatsapp",
    "youtube": "youtube",
    "gmail": "gmail",
    "wordpress": "wordpress",
    "drupal": "drupal",
    "laravel": "laravel",
    "atom": "atom",
    "cloudflare": "cloudflare",
    "cpanel": "cpanel",
    "ffmpeg": "ffmpeg",
    "selenium": "selenium",
    "teamviewer": "teamviewer",
    "virtualbox": "virtualbox",
    "sharepoint": "microsoftsharepoint",
    "nodejs": "nodedotjs",
}

COMMONS_FILE = {
    "python": "File:Python-logo-notext.svg",
    "php": "File:PHP-logo.svg",
    "docker": "File:Moby-logo.png",
    "git": "File:Git-logo.svg",
    "nix": "File:Tux.svg",
    "android": "File:Android robot.svg",
    "java": "File:Java programming language logo.svg",
    "javascript": "File:JavaScript-logo.png",
    "html": "File:HTML5 logo and wordmark.svg",
    "css": "File:CSS3 logo and wordmark.svg",
    "rss": "File:Feed-icon.svg",
    "blender": "File:Blender logo no text.svg",
    "gimp": "File:The GIMP icon - gnome.svg",
    "inkscape": "File:Inkscape Logo.svg",
    "mysql": "File:MySQL textlogo.svg",
    "postgresql": "File:Postgresql elephant.svg",
    "wordpress": "File:WordPress logo.svg",
    "markdown": "File:Markdown-mark.svg",
    "latex": "File:LaTeX project logo red.svg",
    "vi": "File:Vimlogo.svg",
    "apache_httpd": "File:Apache HTTP server logo (2019).svg",
    "license": "File:CC-logo.svg",
    "nfc": "File:NFC logo.svg",
    "windows": "File:Windows 11 Logo.svg",
    "github": "File:Octicons-mark-github.svg",
    "typescript": "File:Typescript logo 2020.svg",
    "r": "File:R logo.svg",
    "spring_boot": "File:Spring Boot.svg",
    "angular": "File:Angular icon 2024.svg",
    "steam": "File:Steam icon logo.svg",
    "unity": "File:Unity 2021.svg",
    "vs_code": "File:Visual Studio Code 1.35 icon.svg",
    "eclipse": "File:Eclipse-Luna-Logo.svg",
    "origin": "File:Origin.svg",
    "wget": "File:GNU Wget.png",
    "mermaid": "File:Mermaid Logo.svg",
    "mercurial": "File:Mercurial logo wide.svg",
    "cpp": "File:ISO C++ Logo.svg",
    "groovy": "File:Groovy-logo.svg",
    "google_api": "File:Google APIs.svg",
    "google_cloud_platform_functions": "File:Google Cloud Functions logo.svg",
    "ftp": "File:FTP icon.svg",
    "putty": "File:PuTTY icon.png",
    "virtualbox": "File:Virtualbox logo.png",
    "windows_terminal": "File:Windows Terminal Logo.svg",
    "microsoft_office": "File:Microsoft 365 logo.svg",
    "microsoft_visual_studio": "File:Visual Studio Icon 2022.svg",
    "adobe_illustrator": "File:Adobe Illustrator CC icon.svg",
    "certbot": "File:Let's Encrypt logo.svg",
    "free_download_manager": "File:FDM Logo.png",
    "sed": "File:Gnu-head.svg",
    "wol": "File:Wake on LAN.svg",
    "email": "File:Mail_(iOS).svg",
    "algorithms": "File:Sorting quicksort anim.gif",
    "cap_theorem": "File:CAP Theorem.svg",
    "nant": "File:Apache Ant Logo.svg",
    "powershell": "File:PowerShell 5.0 icon.png",
    "wget": "File:Gnu-head.svg",
    "wix": "File:WiX toolset logo.png",
    "digital_certificate": "File:Padlock.svg",
    "hardware": "File:Motherboard ASUS P5Q3.jpg",
    "llm": "File:Artificial neural network.svg",
    "machine_learning": "File:Machine Learning Technique.png",
    "proxy": "File:Proxy concept en.svg",
    "ajax": "File:AJAX logo by gengns.svg",
    "http": "File:HTTP logo.svg",
    "xml": "File:XML.svg",
    "json": "File:JSON vector logo.svg",
    "awk": "File:Awk Logo.svg",
    "regex": "File:Regexp-linux-highlight.png",
    "versioning": "File:Git-logo.svg",
    "winapi": "File:Windows logo - 2021.svg",
    "wix": "File:WiX toolset logo.png",
    "lines_of_code": "File:Source code in vim.png",
    "nant": "File:NAnt-logo.png",
    "log4j": "File:Apache Log4j.svg",
    "servlet": "File:Jakarta ee logo.svg",
    "jsp": "File:Jakarta ee logo.svg",
    "fusionchart": "File:Fusioncharts company logo.png",
    "logitech_lua": "File:Lua-Logo.svg",
    "cygwin": "File:Cygwin logo.svg",
    "ios": "File:Apple logo black.svg",
    "mac": "File:MacOS Sequoia Logo 2024.svg",
    "notepad": "File:Notepad.svg",
    "grub": "File:GNU GRUB logo.svg",
    "gscript": "File:Google Apps Script.svg",
    "gtalk": "File:Google Talk icon.svg",
    "ie": "File:Internet Explorer 10+11 logo.svg",
    "internet_explorer": "File:Internet Explorer 10+11 logo.svg",
    "installshield": "File:InstallShield Logo.svg",
    "db2": "File:Logo IBM DB2.png",
    "amd_crimson": "File:AMD Radeon Software logo.svg",
    "amazon_cloud_reader": "File:Amazon Kindle logo.svg",
    "mysql": "File:MySQL textlogo.svg",
}

ALLOWED_LICENSE_NEEDLES = (
    "cc by",
    "cc-by",
    "cc0",
    "creative commons zero",
    "public domain",
    "pd-textlogo",
    "pd-text",
    "pd-ineligible",
    "pd-shape",
    "pd-logo",
    "wtfpl",
    "mpl",
    "mozilla",
    "apache",
    "mit license",
    "bsd",
)


class MLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.fed: list[str] = []

    def handle_data(self, d: str) -> None:
        self.fed.append(d)

    def get_data(self) -> str:
        return re.sub(r"\s+", " ", "".join(self.fed)).strip()


def strip_html(html: str) -> str:
    if not html:
        return ""
    s = MLStripper()
    try:
        s.feed(html)
        s.close()
        return s.get_data()
    except Exception:
        return re.sub(r"<[^>]+>", "", html)


def http_json(url: str, params: dict | None = None) -> dict:
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, context=CTX, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, context=CTX, timeout=60) as resp:
        return resp.read()


def license_ok(short: str, usage: str) -> bool:
    blob = f"{short} {usage}".lower()
    if any(x in blob for x in ("fair use", "non-free", "nonfree", "all rights reserved")):
        return False
    if "gfdl" in blob and "cc" not in blob:
        return False
    return any(n in blob for n in ALLOWED_LICENSE_NEEDLES)


def commons_imageinfo(title: str) -> dict | None:
    data = http_json(
        COMMONS_API,
        {
            "action": "query",
            "format": "json",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url|mime|size|extmetadata",
            "iiurlwidth": "1200",
        },
    )
    pages = data.get("query", {}).get("pages", {})
    page = next(iter(pages.values()), None)
    if not page or "imageinfo" not in page:
        return None
    info = page["imageinfo"][0]
    meta = info.get("extmetadata", {}) or {}

    def mget(key: str) -> str:
        val = meta.get(key) or {}
        return strip_html(val.get("value") or "")

    short = mget("LicenseShortName") or mget("License")
    usage = mget("UsageTerms")
    if not license_ok(short, usage):
        return None
    url = info.get("thumburl") or info.get("url")
    if not url:
        return None
    artist = mget("Artist") or mget("Attribution") or mget("Credit")
    artist = re.sub(r"(Unknown author)+", "Unknown author", artist or "")
    license_url = mget("LicenseUrl")
    file_page = page.get("canonicalurl") or (
        "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
    )
    return {
        "title": title,
        "url": url,
        "original_url": info.get("url"),
        "mime": info.get("mime") or "",
        "author": artist or "Wikimedia Commons contributors",
        "license": short or usage or "See file page",
        "license_url": license_url,
        "file_page": file_page,
        "restrictions": mget("Restriction"),
        "attribution_required": (mget("AttributionRequired") or "").lower() in ("true", "1", "yes"),
    }


def commons_search(query: str) -> list[str]:
    data = http_json(
        COMMONS_API,
        {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": query,
            "srnamespace": "6",
            "srlimit": "8",
        },
    )
    titles = []
    for hit in data.get("query", {}).get("search", []):
        title = hit.get("title") or ""
        low = title.lower()
        if any(bad in low for bad in ("screenshot", "photo of", "poster", "box art", ".pdf")):
            continue
        if not any(ok in low for ok in ("logo", "icon", "wordmark", "logotype", "mark.svg", "robot", "tux")):
            continue
        titles.append(title)
    return titles


SKIP_SEARCH = {
    "rss",
    "wget",
    "groovy",
    "wix",
    "java",
    "eclipse",
    "steam",
    "origin",
    "unity",
    "mermaid",
    "nix",
    "wol",
    "nant",
    "cap_theorem",
    "sed",
    "free_download_manager",
}


def pick_commons(folder_key: str, display: str) -> dict | None:
    forced = COMMONS_FILE.get(folder_key)
    if forced:
        try:
            info = commons_imageinfo(forced)
            if info:
                return info
        except Exception:
            pass
    if folder_key in SKIP_SEARCH:
        return None
    queries = [
        SEARCH_OVERRIDE.get(folder_key, f"{display} logo"),
        f"{display} logo svg",
        f"{display} icon",
    ]
    seen = set()
    for q in queries:
        try:
            titles = commons_search(q)
        except Exception:
            continue
        time.sleep(0.08)
        for title in titles:
            if title in seen:
                continue
            seen.add(title)
            try:
                info = commons_imageinfo(title)
            except Exception:
                info = None
            time.sleep(0.08)
            if info:
                return info
    return None


def load_simple_icons() -> dict[str, dict]:
    raw = http_bytes(SIMPLE_ICONS_JSON)
    icons = json.loads(raw.decode("utf-8"))
    by_slug = {}
    if isinstance(icons, dict) and "icons" in icons:
        seq = icons["icons"]
    else:
        seq = icons
    for icon in seq:
        slug = icon.get("slug") or ""
        by_slug[slug] = icon
    return by_slug


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def pick_simple_icon(folder_key: str, display: str, icons: dict[str, dict]) -> dict | None:
    slug = SIMPLE_SLUG_OVERRIDE.get(folder_key, "AUTO")
    if slug is None:
        return None
    icon = None
    if slug != "AUTO" and slug in icons:
        icon = icons[slug]
    if icon is None:
        n = norm(folder_key)
        n2 = norm(display)
        for s, ic in icons.items():
            if s == n or norm(ic.get("title") or "") in {n, n2} or s == n2:
                icon = ic
                slug = s
                break
    if icon is None:
        return None
    hex_color = icon.get("hex") or "40516F"
    svg_url = f"https://raw.githubusercontent.com/simple-icons/simple-icons/15.22.0/icons/{slug}.svg"
    source = icon.get("source") or f"https://simpleicons.org/{slug}"
    return {
        "title": f"simple-icons/{slug}",
        "url": svg_url,
        "original_url": f"https://cdn.jsdelivr.net/npm/simple-icons@15/icons/{slug}.svg",
        "mime": "image/svg+xml",
        "author": "Simple Icons contributors",
        "license": "CC0 1.0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "file_page": f"https://github.com/simple-icons/simple-icons/blob/15.0.0/icons/{slug}.svg",
        "restrictions": "Trademark of the respective brand; used here for identification",
        "attribution_required": False,
        "brand_source": source,
        "hex": hex_color,
        "repository": "Simple Icons",
    }


BRAND_BLUE = "#56b4d1"


def colorize_svg(svg: str) -> str:
    if re.search(r"<svg\b[^>]*\bfill=", svg, re.I):
        svg = re.sub(
            r'(<svg\b[^>]*\bfill=)["\'][^"\']*["\']',
            rf'\1"{BRAND_BLUE}"',
            svg,
            count=1,
            flags=re.I,
        )
    else:
        svg = re.sub(r"<svg\b", f'<svg fill="{BRAND_BLUE}"', svg, count=1, flags=re.I)
    svg = re.sub(r'fill=["\']#0{3,8}["\']', f'fill="{BRAND_BLUE}"', svg, flags=re.I)
    svg = re.sub(r"fill=['\"]black['\"]", f'fill="{BRAND_BLUE}"', svg, flags=re.I)
    return svg


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".__tmp__" + path.suffix)
    tmp.write_bytes(data)
    tmp.replace(path)


def slug_to_resource_dir(slug: str, resource_root: Path) -> Path:
    parts = [p for p in slug.split("/") if p]
    cur = resource_root
    for part in parts:
        if not cur.is_dir():
            cur = cur / part.capitalize() if part == parts[0] else cur / part
            continue
        match = None
        for child in cur.iterdir():
            if child.is_dir() and child.name.lower() == part.lower():
                match = child
                break
        if match is None:
            name = part[:1].upper() + part[1:] if part else part
            if part.lower() in {"os", "ios"}:
                name = {"os": "OS", "ios": "Ios"}[part.lower()]
            match = cur / name
        cur = match
    return cur


def is_svg_source(url: str, mime: str = "") -> bool:
    blob = f"{url} {mime}".lower()
    return "svg" in blob


def save_svg_cover(dest_dir: Path, svg_text: str, colorize: bool) -> Path:
    if colorize:
        svg_text = colorize_svg(svg_text)
    dest = dest_dir / "index.svg"
    write_atomic(dest, svg_text.encode("utf-8"))
    jpg = dest_dir / "index.jpg"
    if jpg.exists():
        jpg.unlink()
    return dest


def upsert_url_tsv(url_tsv: Path, slug: str, ext: str) -> None:
    parts = slug.strip("/").split("/")
    name = parts[-1]
    parent = "/".join(parts[:-1])
    path_field = f"{parent}/" if parent else ""
    key = (path_field.lower(), name.lower())
    text = url_tsv.read_text(encoding="utf-8") if url_tsv.exists() else "Path\tName\tExtension\n"
    lines = text.splitlines()
    out = []
    found = False
    for line in lines:
        cols = line.split("\t")
        if len(cols) >= 3 and (cols[0].lower(), cols[1].lower()) == key:
            cols[2] = ext
            out.append("\t".join(cols))
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{path_field}\t{name}\t{ext}")
    url_tsv.write_text("\n".join(out) + "\n", encoding="utf-8")


def to_jpeg(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmds = []
    if src.suffix.lower() == ".svg":
        colored = src.with_name(src.stem + ".brand.svg")
        colored.write_text(colorize_svg(src.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")
        src = colored
        cmds.append([
            "magick",
            "-density",
            "512",
            "-background",
            "none",
            str(src),
            "-resize",
            "880x620>",
            "-gravity",
            "center",
            "-background",
            "#f4f6f8",
            "-extent",
            "1024x768",
            "-quality",
            "88",
            str(dest),
        ])
    else:
        cmds.append([
            "magick",
            str(src) + "[0]",
            "-background",
            "#f4f6f8",
            "-alpha",
            "remove",
            "-alpha",
            "off",
            "-resize",
            "880x620>",
            "-gravity",
            "center",
            "-extent",
            "1024x768",
            "-quality",
            "88",
            str(dest),
        ])
        cmds.append([
            "magick",
            str(src),
            "-resize",
            "880x620>",
            "-background",
            "#f4f6f8",
            "-gravity",
            "center",
            "-extent",
            "1024x768",
            str(dest),
        ])
    last_err = None
    for cmd in cmds:
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return
        except subprocess.CalledProcessError as exc:
            last_err = exc
    from PIL import Image, ImageOps

    im = Image.open(src)
    im = ImageOps.exif_transpose(im)
    if im.mode in ("P", "RGBA", "LA"):
        rgba = im.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (244, 246, 248, 255))
        im = Image.alpha_composite(bg, rgba).convert("RGB")
    else:
        im = im.convert("RGB")
    im.thumbnail((880, 620), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (1024, 768), (244, 246, 248))
    canvas.paste(im, ((1024 - im.width) // 2, (768 - im.height) // 2))
    canvas.save(dest, "JPEG", quality=88, optimize=True)
    if last_err and not dest.exists():
        raise last_err


def child_dirs() -> list[tuple[str, Path]]:
    out = []
    for cat in CATEGORIES:
        base = RESOURCE / cat
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir():
                out.append((cat, child))
    return out


def slug_for(cat: str, folder: str) -> str:
    return f"computer/{cat.lower()}/{folder.lower()}"


def relative_resource(path: Path) -> str:
    try:
        return path.relative_to(RESOURCE.parent).as_posix()
    except ValueError:
        return path.as_posix()


def main() -> int:
    icons = {}
    try:
        icons = load_simple_icons()
        print(f"Loaded {len(icons)} Simple Icons")
    except Exception as exc:
        print(f"Simple Icons catalog failed: {exc}")

    rows = []
    tmp = Path(tempfile.mkdtemp(prefix="ujnotes-covers-"))
    children = child_dirs()
    print(f"First-child folders: {len(children)}")

    for cat, folder in children:
        key = folder.name.lower()
        display = folder.name.replace("_", " ")
        jpg = folder / "index.jpg"
        rel = relative_resource(jpg)
        slug = slug_for(cat, folder.name)
        if jpg.exists():
            backup = BACKUP / cat / folder.name / "index.jpg"
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                backup.write_bytes(jpg.read_bytes())
        info = None
        repository = ""
        notes = ""
        prefer_simple = cat in ("OS", "Program", "Programming")
        if prefer_simple and icons:
            try:
                info = pick_simple_icon(key, display, icons)
                if info:
                    repository = "Simple Icons"
            except Exception as exc:
                notes = f"simple-icons error: {exc}"
        if info is None:
            try:
                info = pick_commons(key, display)
                if info:
                    repository = "Wikimedia Commons"
            except Exception as ext:
                notes = (notes + f" commons error: {ext}").strip()
        if info is None and not prefer_simple and icons:
            try:
                info = pick_simple_icon(key, display, icons)
                if info:
                    repository = "Simple Icons"
            except Exception as exc:
                notes = (notes + f" simple-icons error: {exc}").strip()

        status = "unresolved"
        if info:
            ext = ".svg" if "svg" in (info.get("mime") or "") or info["url"].lower().endswith(".svg") else ".bin"
            if "png" in (info.get("mime") or "") or info["url"].lower().endswith(".png"):
                ext = ".png"
            elif "jpeg" in (info.get("mime") or "") or info["url"].lower().endswith((".jpg", ".jpeg")):
                ext = ".jpg"
            raw = tmp / (slug.replace("/", "_") + ext)
            try:
                raw.write_bytes(http_bytes(info["url"]))
                to_jpeg(raw, jpg)
                status = "replaced"
            except Exception as exc:
                notes = (notes + f" download/convert: {exc}").strip()
                status = "unresolved"
        else:
            notes = (notes + " no free replacement found").strip()
            status = "unresolved"

        rows.append(
            {
                "relative_path": rel if status == "replaced" else relative_resource(folder / "index.jpg"),
                "slug": slug,
                "title": display,
                "category": cat,
                "status": status,
                "repository": repository or "",
                "file_page_url": (info or {}).get("file_page", ""),
                "source_url": (info or {}).get("original_url") or (info or {}).get("url", ""),
                "author": (info or {}).get("author", ""),
                "license": (info or {}).get("license", ""),
                "license_url": (info or {}).get("license_url", ""),
                "attribution_required": "yes" if (info or {}).get("attribution_required") else "no",
                "restrictions": (info or {}).get("restrictions", ""),
                "brand_source": (info or {}).get("brand_source", ""),
                "notes": notes,
            }
        )
        print(f"{status:11} {slug:48} {repository:18} {(info or {}).get('license', '')}")

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "relative_path",
        "slug",
        "title",
        "category",
        "status",
        "repository",
        "file_page_url",
        "source_url",
        "author",
        "license",
        "license_url",
        "attribution_required",
        "restrictions",
        "brand_source",
        "notes",
    ]
    with CSV_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    replaced = sum(1 for r in rows if r["status"] == "replaced")
    unresolved = sum(1 for r in rows if r["status"] == "unresolved")
    print(f"Wrote {CSV_PATH}")
    print(f"replaced={replaced} unresolved={unresolved} total={len(rows)}")
    return 0 if unresolved < len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
