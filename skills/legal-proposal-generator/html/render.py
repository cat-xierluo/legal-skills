import argparse
import base64
import re
from html import escape
from pathlib import Path
from string import Template
from urllib.parse import unquote, urlsplit


COVER_FIELDS = {"client": "委托方", "lawyer": "承办律师", "date": "编制日期"}
IMAGE_SIGNATURES = {".png": b"\x89PNG\r\n\x1a\n", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff"}


def read_proposal(source):
    lines = source.read_text(encoding="utf-8-sig").splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        raise ValueError("方案须以 --- 包围的单行键值封面字段开头")
    boundary = lines.index("---", 1)
    metadata = {}
    for line in lines[1:boundary]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        field = re.fullmatch(r"([\w-]+):\s*(.*?)\s*", line)
        if not field or field[1] in metadata:
            raise ValueError("封面字段须使用不重复的单行键值")
        value = field[2]
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        metadata[field[1]] = value.strip()
    for key in ("law_firm", *COVER_FIELDS):
        if not metadata.get(key):
            raise ValueError(f"封面缺少 {key}")
    return metadata, "\n".join(lines[boundary + 1:])


def embed_image(root, reference):
    url = urlsplit(reference)
    relative = Path(unquote(url.path))
    if url.scheme or url.netloc or url.query or url.fragment or relative.is_absolute():
        raise ValueError("图件须为方案目录内的相对 PNG 或 JPEG 路径")
    target = (root / relative).resolve()
    suffix = target.suffix.lower()
    if not target.is_relative_to(root) or suffix not in IMAGE_SIGNATURES or not target.is_file():
        raise ValueError("图件须为方案目录内已有的 PNG 或 JPEG 文件")
    limit = 8 * 1024 * 1024
    with target.open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit or not content.startswith(IMAGE_SIGNATURES[suffix]):
        raise ValueError("图件格式与扩展名不符，或大小超过 8 MiB")
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


def create_parser():
    from markdown_it import MarkdownIt
    from markdown_it.rules_block.table import escapedSplit, getLine, table

    markdown = MarkdownIt("commonmark", {"html": False}).enable("table")

    def cell_count(state, line):
        cells = escapedSplit(getLine(state, line).strip())
        if cells and not cells[0]:
            cells.pop(0)
        if cells and not cells[-1]:
            cells.pop()
        return len(cells)

    def strict_table(state, start, end, silent):
        matched = table(state, start, end, silent)
        if matched and not silent:
            width = cell_count(state, start)
            for line in range(start + 2, state.line):
                if cell_count(state, line) != width:
                    raise ValueError(f"表格第 {line + 1} 行的列数与表头不一致")
        return matched

    markdown.block.ruler.at("table", strict_table, {"alt": ["paragraph", "reference"]})
    return markdown


def heading_text(heading):
    return "".join(
        child.content for child in heading.children or []
        if child.type in ("text", "code_inline", "image")
    )


def render_proposal(source):
    metadata, body = read_proposal(source)
    markdown = create_parser()
    tokens = markdown.parse(body)
    if len(tokens) <= 3 or tokens[0].type != "heading_open" or tokens[0].tag != "h1":
        raise ValueError("正文须从一个一级标题开始，并包含方案内容")
    if any(token.type == "heading_open" and token.tag == "h1" for token in tokens[3:]):
        raise ValueError("方案只能有一个一级标题")
    title = heading_text(tokens[1])
    if not title.strip():
        raise ValueError("一级标题须包含方案名称")
    if metadata.get("title", title) != title:
        raise ValueError("封面 title 与正文一级标题不一致")

    contents = []
    for index, token in enumerate(tokens):
        if token.type == "heading_open" and token.tag == "h2" and token.level == 0:
            chapter = f"chapter-{len(contents) + 1}"
            token.attrSet("id", chapter)
            label = escape(heading_text(tokens[index + 1]))
            contents.append(f'<li><a href="#{chapter}">{label}</a></li>')
        for child in token.children or []:
            if child.type == "image":
                child.attrSet("src", embed_image(source.parent.resolve(), child.attrGet("src")))
            if child.type == "link_open":
                url = urlsplit(child.attrGet("href"))
                if url.scheme not in ("http", "https") or not url.hostname:
                    raise ValueError("正文链接须为可独立打开的 HTTP(S) 来源")

    cover_details = "".join(
        f"<div><dt>{label}</dt><dd>{escape(metadata[key])}</dd></div>"
        for key, label in COVER_FIELDS.items()
    )
    subtitle = metadata.get("subtitle", "")
    heading = markdown.renderer.renderInline(tokens[1].children, markdown.options, {})
    article = markdown.renderer.render(tokens[3:], markdown.options, {})
    article = article.replace("<table>", '<div class="table-scroll"><table>').replace("</table>", "</table></div>")
    navigation = ""
    if contents:
        navigation = '<nav class="contents" aria-label="目录"><h2>目录</h2><ol>' + "".join(contents) + "</ol></nav>"
    template = Template(Path(__file__).with_name("proposal.html").read_text(encoding="utf-8"))
    return template.substitute(
        title=escape(title),
        heading=heading,
        law_firm=escape(metadata["law_firm"]),
        subtitle=f'<p class="subtitle">{escape(subtitle)}</p>' if subtitle else "",
        cover_details=cover_details,
        navigation=navigation,
        article=article,
    )


def main():
    parser = argparse.ArgumentParser(description="将已核定的法律服务方案 Markdown 排成单文件 HTML")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    try:
        if options.output.suffix.lower() != ".html":
            raise ValueError("输出文件扩展名须为 .html")
        document = render_proposal(options.input)
        with options.output.open("x", encoding="utf-8") as output:
            output.write(document)
    except ModuleNotFoundError:
        parser.exit(1, "需要 markdown-it-py，请参见设计版 HTML 使用说明。\n")
    except (OSError, ValueError) as error:
        parser.exit(1, f"无法生成 HTML：{error}\n")


if __name__ == "__main__":
    main()
