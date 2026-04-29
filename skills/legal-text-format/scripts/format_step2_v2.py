#!/usr/bin/env python3
"""
Step 2 formatter v2 - precise legal text formatting.
Handles punctuation carefully (not inside URLs/markdown), proper header structure.
"""
import re
import os

def smart_punct_replace(text):
    """
    Convert English punctuation to Chinese, but be smart about it:
    - Don't replace inside URLs (http://, https://)
    - Don't replace inside markdown links [text](url)
    - Don't replace inside image syntax ![alt](url)
    - Don't replace inside code blocks
    """
    # Protect URLs first by temporarily replacing with placeholders
    urls = []
    def protect_url(m):
        urls.append(m.group(0))
        return f'__URL_PLACEHOLDER_{len(urls)-1}__'
    text = re.sub(r'https?://[^\s\'\"）\)\]]+', protect_url, text)
    
    # Protect markdown links [text](url) 
    md_links = []
    def protect_md_link(m):
        md_links.append(m.group(0))
        return f'__MDLINK_PLACEHOLDER_{len(md_links)-1}__'
    text = re.sub(r'\[([^\]]*)\]\(([^)]+)\)', protect_md_link, text)
    
    # Protect image syntax too
    md_images = []
    def protect_md_image(m):
        md_images.append(m.group(0))
        return f'__MDIMAGE_PLACEHOLDER_{len(md_images)-1}__'
    text = re.sub(r'!\[[^\]]*\]\([^)]+\)', protect_md_image, text)
    
    # Now safe to replace punctuation (only in text, not in placeholders)
    punct_map = [
        (r'\(', '（'), (r'\)', '）'),
        (r',', '，'), (r'\.', '。'), (r':', '：'), (r';', '；'),
        (r'!', '！'), (r'\?', '？'),
    ]
    for pattern, repl in punct_map:
        text = re.sub(pattern, repl, text)
    
    # Restore URLs
    for i, url in enumerate(urls):
        text = text.replace(f'__URL_PLACEHOLDER_{i}__', url)
    
    # Restore markdown links (keep as-is, punctuation already converted)
    for i, link in enumerate(md_links):
        text = text.replace(f'__MDLINK_PLACEHOLDER_{i}__', link)
    
    # Restore markdown images
    for i, img in enumerate(md_images):
        text = text.replace(f'__MDIMAGE_PLACEHOLDER_{i}__', img)
    
    return text

def process_file(input_path, output_path, court_name, source_url, title):
    with open(input_path, 'r', encoding='utf-8') as f:
        raw = f.read()
    
    # Find body start - first "4月XX日" paragraph
    body_start = 0
    for marker in ['4月23日', '4月24日', '4月22日', '4月21日', '4月20日']:
        idx = raw.find(marker)
        if idx != -1:
            line_start = raw.rfind('\n', 0, idx) + 1
            body_start = line_start
            break
    
    body = raw[body_start:]
    
    # Find body end - look for last case's typical meaning section
    # Find last "典型意义" position
    last_meaning = body.rfind('典型意义')
    if last_meaning > 0:
        # Find the end of that section
        tail_start = last_meaning
        tail = body[tail_start:tail_start+2000]
        
        # Look for next case pattern or footer
        next_patterns = [
            r'来源\s*[:：]',
            r'\n\s*扫码获取',
            r'\n\s*浏览知产财经',
            r'\n\s*联系我们',
            r'\n\s*点分享',
            r'\n\s*END\n',
        ]
        cut_pos = len(body)
        for pat in next_patterns:
            m = re.search(pat, tail)
            if m:
                cut_pos = min(cut_pos, tail_start + m.start())
        
        # If no clear footer, look for a natural break after last meaning
        if cut_pos == len(body):
            # Find a paragraph break after last meaning
            snippet = body[last_meaning:last_meaning+1500]
            # Find the last paragraph end
            paras = re.findall(r'.+?(?=\n\n)', snippet, re.DOTALL)
            if paras:
                last_para_end = last_meaning
                for p in paras:
                    last_para_end = body.find(p, last_meaning) + len(p)
                cut_pos = last_para_end
        
        body = body[:cut_pos]
    
    # Remove trailing promotional sections more aggressively
    for footer_kw in ['来源', '扫码', '知产财经', '联系我们', '订阅我们', '点分享', '点收藏', '点在看', '点点赞', 'END', '往期热文', '文章原文']:
        # Find last occurrence
        last_pos = 0
        for m in re.finditer(re.escape(footer_kw), body):
            # Check if this is in a meaningful context (not case content)
            before = body[max(0, m.start()-200):m.start()]
            if any(kw in before for kw in ['典型意义', '裁判结果', '案情摘要', '基本案情']):
                continue  # This is within case content
            last_pos = m.start()
        if last_pos > 0:
            body = body[:last_pos]
    
    # Apply punctuation conversion (smart)
    body = smart_punct_replace(body)
    
    # Now format headers
    lines = body.split('\n')
    result_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Skip empty lines at start
        if not stripped and i < 5:
            i += 1
            continue
        
        # Skip obvious promotional/navigation lines
        skip_patterns = [
            r'^[\s]*data-sanitized-class',
            r'^[\s]*$',  # Will add back properly
            r'^▴',  # Navigation markers
            r'^点分享',
            r'^点收藏',
            r'^点在看',
            r'^点点赞',
            r'^订阅我们',
            r'^联系我们',
            r'^知产财经',
            r'^浏览知产财经',
            r'^扫码获取',
            r'^查看.*专题',
            r'^往期热文',
            r'^!\[\]\(http',  # Broken image tags
            r'^data-',  # data attributes in text
        ]
        
        if any(re.match(pat, stripped) for pat in skip_patterns):
            i += 1
            continue
        
        # Skip lines that are just decorative
        if re.match(r'^[_\-=*]{3,}$', stripped):
            i += 1
            continue
        
        # Skip lines that look like HTML remnants
        if stripped.startswith('![](http') or stripped.startswith('!['):
            i += 1
            continue
        
        # Skip lines that are just page indicators
        if '向上滑动' in stripped or 'data-sanitized' in stripped:
            i += 1
            continue
        
        # Process case title markers /** 案例X **/
        if re.match(r'/\*\*\s*案例\s*\d+\s*\*/', stripped) or \
           re.match(r'\*\*\s*案例\s*\d+\s*\*\*', stripped):
            # Get next line for case name
            case_name = ''
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and not next_line.startswith('#') and '案情' not in next_line and '裁判' not in next_line and '典型' not in next_line:
                    case_name = next_line
                    i += 1
                else:
                    # Extract from current line
                    case_name = re.sub(r'/\*\*|\*\*|案例\s*\d+\s*[/\*]*', '', stripped).strip()
            result_lines.append(f'\n## {case_name}\n')
            i += 1
            continue
        
        # Process case title patterns like "案例1" on its own line
        if re.match(r'^案例\s*\d+\s*[/因素]*$', stripped) or \
           re.match(r'^案例[一二三四五六七八九十]+$', stripped):
            result_lines.append(f'\n## [CASE_NAME_MISSING]\n')
            i += 1
            continue
        
        # Process section headers in bold **案情摘要**, **裁判结果**, **典型意义**
        if stripped.startswith('**') and stripped.endswith('**'):
            inner = stripped.strip('*')
            if inner in ['案情摘要', '基本案情', '裁判结果', '典型意义', '裁判内容', '入选理由及解读']:
                result_lines.append(f'\n### {inner}\n')
                i += 1
                continue
        
        # Process "【案情摘要】" style headers
        if re.match(r'^【(案情摘要|基本案情|裁判结果|典型意义|裁判内容|入选理由及解读)】$', stripped):
            inner = re.sub(r'【|】', '', stripped)
            result_lines.append(f'\n### {inner}\n')
            i += 1
            continue
        
        # Skip lines that are just sources e.g. "来源：上海市高级人民法院"
        if re.match(r'^\s*来源\s*[:：]\s*(上海|天津|青岛|湖南|宁波|江苏|南京|最高|北京|浙江|广东|山东|四川|重庆|湖北|河北|辽宁|福建|河南|[一二三四五六七八九十]+)', stripped):
            i += 1
            continue
        
        # Skip "来源 |" lines
        if re.match(r'^\s*来源\s*\|', stripped):
            i += 1
            continue
        
        result_lines.append(line)
        i += 1
    
    body = '\n'.join(result_lines)
    
    # Clean excessive blank lines
    body = re.sub(r'\n{3,}', '\n\n', body)
    
    # Convert bold markers that are case markers like **/** **案例1** **/
    # Already handled above
    
    # Remove lines that are just empty or whitespace at the very end
    while body.endswith('\n'):
        if body.endswith('\n\n\n'):
            body = body[:-1]
        else:
            break
    
    # Build final output
    output = f"""# {title}

- **来源**：{court_name}
- **原文**：[点击查看]({source_url})

"""
    output += body
    
    # Final cleanup
    output = re.sub(r'\n{3,}', '\n\n', output)
    
    # Remove trailing blank lines
    output = output.rstrip() + '\n'
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output)
    
    print(f"Written: {output_path}")

def main():
    base_in = '/Users/maoking/Desktop/Clawd/05 - 📡 外部同步/法律法规/'
    base_out = '/Users/maoking/.openclaw/skills/legal-text-format/archive/'
    
    files = [
        ('260424 附判决┃上海高院发布2025年知识产权司法保护典型案例（15件）.md',
         '20260425_120000_上海高院2025年知识产权司法保护典型案例/20260425_上海高院2025年知识产权司法保护典型案例_formatted.md',
         '上海市高级人民法院',
         'http://mp.weixin.qq.com/s?__biz=MzUxMDAwNTI3OQ==&mid=2247532175&idx=2&sn=751cc17ca602a741d0907998de151fbe&chksm=f87a9b84ec2b4bc7b78b84fdbd4bf0ba3827e3eb63f8f9768c93aa60618863f60309595d8d24&scene=0#rd',
         '上海高院发布2025年知识产权司法保护典型案例（15件）'),
        ('260424 附判决┃天津高院发布2025年天津法院知识产权典型案例（7件）.md',
         '20260425_120001_天津高院2025年天津法院知识产权典型案例/20260425_天津高院2025年天津法院知识产权典型案例_formatted.md',
         '天津市高级人民法院',
         'http://mp.weixin.qq.com/s?__biz=MzUxMDAwNTI3OQ==&mid=2247532189&idx=3&sn=3a1b1ab7c375e156918800d365010de4&chksm=f8132c0da197ac9347ebc93310b701ec2fd60fc5d93cab64d9c641836e139c7845e97107bf74&scene=0#rd',
         '天津高院发布2025年天津法院知识产权典型案例（7件）'),
        ('260424 附判决┃青岛中院发布2025年青岛法院知识产权司法保护典型案例（10件）.md',
         '20260425_120002_青岛中院2025年青岛法院知识产权司法保护典型案例/20260425_青岛中院2025年青岛法院知识产权司法保护典型案例_formatted.md',
         '青岛市中级人民法院',
         'http://mp.weixin.qq.com/s?__biz=MzUxMDAwNTI3OQ==&mid=2247532204&idx=2&sn=e220a7465591667168de8d685ce05a8d&chksm=f8c9e4c174bd94ae03bbd21779674c01f5dd9d3ab12a5f6c71180eeed91873fce2ee30b7991d&scene=0#rd',
         '青岛中院发布2025年青岛法院知识产权司法保护典型案例（10件）'),
        ('260424 附判决┃湖南高院发布2025年知识产权司法保护状况及服务保障新质生产力发展典型案.md',
         '20260425_120003_湖南高院2025年知识产权司法保护状况及服务保障新质生产力发展典型案例/20260425_湖南高院2025年知识产权司法保护状况及服务保障新质生产力发展典型案例_formatted.md',
         '湖南省高级人民法院',
         'http://mp.weixin.qq.com/s?__biz=MzUxMDAwNTI3OQ==&mid=2247532189&idx=2&sn=2e4e073bed6c1690a7ede674cb29aec1&chksm=f8b9319c5f542f0b4ca89b8532273823caefe2ec8cf57cae69a39fc78430733517fa3c2ae1bf&scene=0#rd',
         '湖南高院发布2025年知识产权司法保护状况及服务保障新质生产力发展典型案例'),
        ('260424 附判决┃宁波中院发布2025年度宁波法院知识产权审判典型案例（10件）.md',
         '20260425_120004_宁波中院2025年度宁波法院知识产权审判典型案例/20260425_宁波中院2025年度宁波法院知识产权审判典型案例_formatted.md',
         '宁波市中级人民法院',
         'http://mp.weixin.qq.com/s?__biz=MzUxMDAwNTI3OQ==&mid=2247532189&idx=4&sn=a017ba462c773185997706d6d1bd8d5d&chksm=f85c4b3d874dc4d44897ad3cce8fa702f91cb63ec37b2c324217fe6c6e31bd678a408b0926ec&scene=0#rd',
         '宁波中院发布2025年度宁波法院知识产权审判典型案例（10件）'),
        ('260424 附判决┃江苏高院发布2025年服务保障科技创新和产业创新融合知产典型案例（10件.md',
         '20260425_120005_江苏高院2025年服务保障科技创新和产业创新融合知产典型案例/20260425_江苏高院2025年服务保障科技创新和产业创新融合知产典型案例_formatted.md',
         '江苏省高级人民法院',
         'http://mp.weixin.qq.com/s?__biz=MzUxMDAwNTI3OQ==&mid=2247532189&idx=1&sn=69c92887995f2e2d071a934d59a2be7e&chksm=f86160cc32719cb2c3e6d6e564503e2e31c5f59fd13a61e0a25560cc685ed293645966e7be25&scene=0#rd',
         '江苏高院发布2025年服务保障科技创新和产业创新融合知产典型案例（10件）'),
        ('260424 上海高院发布涉商业秘密保护典型案例（10件）.md',
         '20260425_120006_上海高院涉商业秘密保护典型案例/20260425_上海高院涉商业秘密保护典型案例_formatted.md',
         '上海市高级人民法院',
         'http://mp.weixin.qq.com/s?__biz=MzUxMDAwNTI3OQ==&mid=2247532175&idx=1&sn=123ffe43ea091b75c2b3fb633a3e433a&chksm=f81826aa74c0128a9fac0c4918dd2db3b9ea0b6403074b909ee91f132735bd72f2f6813c5ef8&scene=0#rd',
         '上海高院发布涉商业秘密保护典型案例（10件）'),
        ('260424 附判决┃南京中院发布2025年南京法院知识产权十大案例.md',
         '20260425_120007_南京中院2025年南京法院知识产权十大案例/20260425_南京中院2025年南京法院知识产权十大案例_formatted.md',
         '南京市中级人民法院',
         'http://mp.weixin.qq.com/s?__biz=MzUxMDAwNTI3OQ==&mid=2247532204&idx=1&sn=7127f2c0695db3e924509b24a0a2cb27&chksm=f87c7d06daaa5b24f5bc37b84f6fc30ec6c896dfa80a05772a9ad343096f36d00b81b29b5d8f&scene=0#rd',
         '南京中院发布2025年南京法院知识产权十大案例'),
        ('260423 4·26特辑 _ 上海法院发布知识产权审判白皮书和典型案例.md',
         '20260425_120008_上海法院知识产权审判白皮书和典型案例/20260425_上海法院知识产权审判白皮书和典型案例_formatted.md',
         '上海市高级人民法院',
         'http://mp.weixin.qq.com/s?__biz=MjM5NzU5ODEzNw==&mid=2665453880&idx=1&sn=44354253167edd6ec8268facdae0adba&chksm=bcd59bf527ccf9d451cb566915572414243a1c12c9cfc2c49a785cc02bfca32061912c70a4fd&scene=0#rd',
         '上海法院发布知识产权审判白皮书和典型案例'),
    ]
    
    for f in files:
        inp = base_in + f[0]
        outp = base_out + f[1]
        try:
            process_file(inp, outp, f[2], f[3], f[4])
        except Exception as e:
            print(f"Error: {f[0]}: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    main()
