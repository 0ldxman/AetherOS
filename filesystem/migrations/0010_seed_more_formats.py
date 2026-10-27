"""Стартовые записи реестра: ещё настоящие форматы, свои шаблоны и кодировки. Записи только добавляются (get_or_create):
то, что автор уже поправил в админке, не перезаписывается."""
from django.db import migrations

XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

SIGNATURES = {
    # имя: (подпись, расширение, псевдонимы, первые байты в hex)
    "bmp": ("BMP image", ".bmp", "", "42 4d 36 00 0c 00 00 00 00 00 36 00 00 00"),
    "tiff": ("TIFF image", ".tiff", "tif", "49 49 2a 00 08 00 00 00"),
    "webp": ("WebP image", ".webp", "", "52 49 46 46 24 08 00 00 57 45 42 50 56 50 38 20"),
    "ico": ("Windows icon", ".ico", "", "00 00 01 00 01 00 10 10 00 00 01 00 20 00"),
    "psd": ("Photoshop document", ".psd", "", "38 42 50 53 00 01 00 00 00 00 00 00"),
    "ogg": ("Ogg audio", ".ogg", "oga, ogv", "4f 67 67 53 00 02 00 00 00 00 00 00 00 00"),
    "flac": ("FLAC audio", ".flac", "", "66 4c 61 43 00 00 00 22"),
    "mid": ("MIDI music", ".mid", "midi", "4d 54 68 64 00 00 00 06 00 01 00 02 01 e0"),
    "mp4": ("MP4 video", ".mp4", "m4v", "00 00 00 18 66 74 79 70 69 73 6f 6d 00 00 02 00"),
    "mkv": ("Matroska video", ".mkv", "", "1a 45 df a3 9f 42 86 81 01 42 f7 81 01"),
    "avi": ("AVI video", ".avi", "", "52 49 46 46 24 08 00 00 41 56 49 20 4c 49 53 54"),
    "7z": ("7-Zip archive", ".7z", "", "37 7a bc af 27 1c 00 04"),
    "rar": ("RAR archive", ".rar", "", "52 61 72 21 1a 07 00"),
    "bz2": ("BZip2 archive", ".bz2", "", "42 5a 68 39 31 41 59 26 53 59"),
    "xz": ("XZ archive", ".xz", "", "fd 37 7a 58 5a 00 00 04"),
    "exe": ("Windows executable", ".exe", "", "4d 5a 90 00 03 00 00 00 04 00 00 00 ff ff 00 00"),
    "dll": ("Windows library", ".dll", "", "4d 5a 90 00 03 00 00 00 04 00 00 00 ff ff 00 00"),
    "elf": ("ELF executable", ".elf", "", "7f 45 4c 46 02 01 01 00 00 00 00 00 00 00 00 00"),
    "class": ("Java class", ".class", "", "ca fe ba be 00 00 00 34"),
    "sqlite": ("SQLite database", ".sqlite", "db3", "53 51 4c 69 74 65 20 66 6f 72 6d 61 74 20 33 00"),
    "pcap": ("Packet capture", ".pcap", "", "d4 c3 b2 a1 02 00 04 00 00 00 00 00 00 00 00 00"),
    "kdbx": ("KeePass database", ".kdbx", "", "03 d9 a2 9a 67 fb 4b b5 01 00 03 00"),
}

LOG = "[{at}] session opened by {who}\n[{at}] ref {ref}\n{body}\n[{at}] session closed\n"
HTML = "<!doctype html>\n<html><head><meta charset=\"utf-8\"><title>{title}</title></head>\n<body>\n{body_html}</body></html>\n"
SVG = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"640\" height=\"480\">\n"
    "<title>{title}</title>\n<text x=\"16\" y=\"32\">{body_xml}</text>\n</svg>\n"
)
RTF = "{{\\rtf1\\ansi\\deff0{{\\fonttbl{{\\f0 Times New Roman;}}}}\\f0\\fs24 {body_rtf}\\par}}\n"
PEM = "-----BEGIN CERTIFICATE-----\n{body_b64}\n-----END CERTIFICATE-----\n"
PGP = "-----BEGIN PGP MESSAGE-----\n\n{body_b64}\n={hash:.4}\n-----END PGP MESSAGE-----\n"
SSH = "-----BEGIN OPENSSH PRIVATE KEY-----\n{body_b64}\n-----END OPENSSH PRIVATE KEY-----\n"
EML = (
    "From: {sender}\nTo: {recipients}\nSubject: {subject}\nDate: {date}\nMessage-ID: <{id}@aether>\nMIME-Version: 1.0\n"
    "Content-Type: text/plain; charset=utf-8\nContent-Transfer-Encoding: 8bit\n\n{body}\n"
)

TEXTS = (
    # имя, подпись, расширение, псевдонимы, шаблон
    ("html", "HTML page", ".html", "htm", HTML),
    ("xml", "XML document", ".xml", "", XML + "<record who=\"{who}\" when=\"{when}\">\n<title>{title}</title>\n<text>{body_xml}</text>\n</record>\n"),
    ("json", "JSON document", ".json", "", '{{\n  "title": "{title}",\n  "who": "{who}",\n  "when": "{when}",\n  "text": "{body_json}"\n}}\n'),
    ("csv", "CSV table", ".csv", "", 'field,value\nwho,{who}\nwhen,{when}\nref,{ref}\ntext,"{body_csv}"\n'),
    ("txt", "Plain text", ".txt", "", "{body}\n"),
    ("md", "Markdown", ".md", "markdown", "# {title}\n\n{body}\n"),
    ("rtf", "Rich text", ".rtf", "", RTF),
    ("svg", "SVG image", ".svg", "", SVG),
    ("eml", "E-mail message", ".eml", "", EML),
    ("pem", "PEM certificate", ".pem", "crt", PEM),
    ("pgp", "PGP message", ".pgp", "asc", PGP),
    ("ssh", "OpenSSH private key", ".ssh", "", SSH),
    ("sh", "Shell script", ".sh", "", "#!/bin/sh\n# {title}\n# {who} {when}\ncat <<'EOF'\n{body}\nEOF\n"),
    ("py", "Python script", ".py", "", '#!/usr/bin/env python3\n# {title}\n# {who} {when}\n"""\n{body}\n"""\n'),
    # свои
    ("log", "Aether LOG (session log)", ".log", "", LOG),
    ("map", "Aether MAP (map scene)", ".map", "", "§map\nscene: {ref}\ntitle: {title}\n---\n{body}\n"),
)

RELS = (
    XML + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="{target}"/>'
    "</Relationships>"
)


def _types(override, content):
    return (
        XML + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="{override}" ContentType="{content}"/></Types>'
    )


CORE = (
    XML + '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{title}</dc:title><dc:creator>{who}</dc:creator></cp:coreProperties>'
)

ZIPS = {
    # имя: (подпись, расширение, [(файл внутри, шаблон)])
    "docx": ("Word document", ".docx", [
        ("[Content_Types].xml", _types("/word/document.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml")),
        ("_rels/.rels", RELS.replace("{target}", "word/document.xml")),
        ("word/document.xml", XML + '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r>'
                                    '<w:t xml:space="preserve">{body_xml}</w:t></w:r></w:p></w:body></w:document>'),
        ("docProps/core.xml", CORE),
    ]),
    "xlsx": ("Excel workbook", ".xlsx", [
        ("[Content_Types].xml", _types("/xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml")),
        ("_rels/.rels", RELS.replace("{target}", "xl/workbook.xml")),
        ("xl/workbook.xml", XML + '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets><sheet name="{title}" sheetId="1"/></sheets></workbook>'),
        ("xl/worksheets/sheet1.xml", XML + '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1">'
                                          '<c r="A1" t="inlineStr"><is><t>{body_xml}</t></is></c></row></sheetData></worksheet>'),
        ("docProps/core.xml", CORE),
    ]),
    "pptx": ("PowerPoint presentation", ".pptx", [
        ("[Content_Types].xml", _types("/ppt/presentation.xml", "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml")),
        ("_rels/.rels", RELS.replace("{target}", "ppt/presentation.xml")),
        ("ppt/presentation.xml", XML + '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldIdLst/></p:presentation>'),
        ("ppt/slides/slide1.xml", XML + '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                                        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:txBody>'
                                        '<a:p><a:r><a:t>{body_xml}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>'),
        ("docProps/core.xml", CORE),
    ]),
    "odt": ("OpenDocument text", ".odt", [
        ("mimetype", "application/vnd.oasis.opendocument.text"),
        ("META-INF/manifest.xml", XML + '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
                                        '<manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>'
                                        '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/></manifest:manifest>'),
        ("content.xml", XML + '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                              'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text>'
                              '<text:p>{body_xml}</text:p></office:text></office:body></office:document-content>'),
        ("meta.xml", XML + '<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                           'xmlns:dc="http://purl.org/dc/elements/1.1/"><office:meta><dc:title>{title}</dc:title>'
                           '<dc:creator>{who}</dc:creator></office:meta></office:document-meta>'),
    ]),
    "epub": ("EPUB book", ".epub", [
        ("mimetype", "application/epub+zip"),
        ("META-INF/container.xml", XML + '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                                         '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'),
        ("OEBPS/content.opf", XML + '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                                    '<dc:title>{title}</dc:title><dc:creator>{who}</dc:creator></metadata><manifest>'
                                    '<item id="t" href="text.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="t"/></spine></package>'),
        ("OEBPS/text.xhtml", XML + '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>{title}</title></head><body>{body_html}</body></html>'),
    ]),
}

ENCODINGS = (
    ("utf32", "UTF-32", "codec", "utf-32-le"),
    ("cp1251", "Windows-1251 (Cyrillic)", "codec", "cp1251"),
    ("koi8r", "KOI8-R (Cyrillic)", "codec", "koi8-r"),
    ("cp866", "CP866 (DOS Cyrillic)", "codec", "cp866"),
    ("utf7", "UTF-7", "codec", "utf-7"),
    ("xor", "XOR with a byte", "xor", "0x5a"),
    ("reverse", "Reversed bytes", "reverse", ""),
    ("base32", "Base32", "base32", ""),
    ("rot47", "ROT47", "rot47", ""),
    ("bin", "Binary digits", "bin", ""),
    ("dec", "Decimal codes", "dec", ""),
    ("oct", "Octal codes", "oct", ""),
    ("url", "Percent-encoding", "url", ""),
    ("base85", "Base85", "base85", ""),
    ("uu", "uuencode", "uu", ""),
    ("atbash", "Atbash", "atbash", ""),
)

# псевдонимы форматов, заведённых раньше
OLD_ALIASES = {"jpg": "jpeg, jpe, jfif", "gz": "gzip"}


def seed(apps, schema_editor):
    Format = apps.get_model("filesystem", "FileFormat")
    Part = apps.get_model("filesystem", "FormatPart")
    Encoding = apps.get_model("filesystem", "FileEncoding")

    for name, (title, extension, aliases, magic) in SIGNATURES.items():
        Format.objects.get_or_create(
            name=name, defaults=dict(title=title, extension=extension, aliases=aliases, kind="signature", magic=magic)
        )

    for name, title, extension, aliases, template in TEXTS:
        Format.objects.get_or_create(
            name=name, defaults=dict(title=title, extension=extension, aliases=aliases, kind="text", template=template)
        )

    for name, (title, extension, files) in ZIPS.items():
        made = Format.objects.get_or_create(
            name=name, defaults=dict(title=title, extension=extension, kind="zip", magic="")
        )
        if made[1]:
            for order, (path, template) in enumerate(files):
                Part.objects.create(format=made[0], order=order, name=path, source="template", value=template)

    for name, aliases in OLD_ALIASES.items():
        Format.objects.filter(name=name, aliases="").update(aliases=aliases)

    for name, title, kind, param in ENCODINGS:
        Encoding.objects.get_or_create(name=name, defaults=dict(title=title, kind=kind, param=param))


class Migration(migrations.Migration):

    dependencies = [
        ("filesystem", "0009_formats_more"),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
