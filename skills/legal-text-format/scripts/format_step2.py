#!/usr/bin/env python3
"""
Step 2 formatter for legal case compilation files.
Processes raw markdown files and outputs formatted versions.
"""
import re
import os
import json

def clean_text(text):
    """Clean and format text according to skill rules."""
    # Remove image tags that are just URLs
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    
    # Convert English punctuation to Chinese
    text = text.replace('(', '（').replace(')', '）')
    text = text.replace(',', '，')
    text = text.replace('.', '。')
    text = text.replace(':', '：')
    text = text.replace(';', '；')
    text = text.replace('!', '！')
    text = text.replace('?', '？')
    
    # Full-width to half-width digits
    fw = '０１２３４５６７８９'
    hw = '0123456789'
    for f, h in zip(fw, hw):
        text = text.replace(f, h)
    
    # Clean excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text

def process_file(input_path, output_path, court_name, source_url, title):
    """Process a single file."""
    with open(input_path, 'r', encoding='utf-8') as f:
        raw = f.read()
    
    # Extract body - find the first content marker (4月XX日)
    marker_found = False
    for marker in ['4月23日', '4月24日', '4月22日', '4月21日', '4月20日']:
        idx = raw.find(marker)
        if idx != -1:
            # Go back to start of that line
            line_start = raw.rfind('\n', 0, idx) + 1
            body = raw[line_start:]
            marker_found = True
            break
    
    if not marker_found:
        # Try to find start after frontmatter
        parts = raw.split('---')
        body = raw
        for part in parts[1:]:
            if any(m in part for m in ['4月', '案例', '案情', '裁判']):
                body = raw[raw.find(part):]
                break
    
    # Remove trailing content (after last case)
    # Find "来源" or "扫码" footer
    footer_patterns = [
        r'\n来源\s*[:：]\s*',
        r'\n\s*来源\s*[:：]',
        r'\n\s*扫码获取',
        r'\n\s*浏览知产财经',
        r'\n\s*联系我们',
        r'\n\s*订阅我们',
        r'\n\s*点分享',
        r'\n\s*END\n',
        r'\n\s*-\{3,\}\n',  # --- separators
    ]
    
    last_good = len(body)
    for fp in footer_patterns:
        matches = list(re.finditer(fp, body))
        if matches:
            for m in reversed(matches):
                # Only cut if this looks like footer (near end)
                if m.start() > len(body) * 0.7:
                    last_good = min(last_good, m.start())
                    break
    
    body = body[:last_good]
    
    # Find actual last case end
    # Look for the last "典型意义" section
    last_meaning = body.rfind('典型意义')
    if last_meaning > 0:
        # Find end of that section - look for next case or footer
        tail = body[last_meaning:]
        # Find good cut point - usually a paragraph break after the last meaning
        meaning_end = last_meaning + 500
        for i in range(last_meaning + 300, min(len(body), last_meaning + 1000)):
            if body[i] == '\n' and body[i-1] == '\n':
                # Check if we're past the last case content
                snippet = body[i:i+100]
                if any(kw in snippet for kw in ['来源', '扫码', '知产财经', '联系我们', 'END', '往期']):
                    meaning_end = i
                    break
                elif i - last_meaning > 800:
                    meaning_end = i
                    break
        body = body[:meaning_end]
    
    body = clean_text(body)
    
    # Build output
    output = f"""# {title}

- **来源**：{court_name}
- **原文**：[点击查看]({source_url})

"""
    
    output += body
    
    # Final cleanup
    output = re.sub(r'\n{3,}', '\n\n', output)
    
    # Remove trailing blank lines
    while output.endswith('\n\n'):
        output = output[:-1]
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output)
    
    print(f"Written: {output_path}")

def main():
    base_in = '/Users/maoking/Desktop/Clawd/05 - 📡 外部同步/法律法规/'
    base_out = '/Users/maoking/.openclaw/skills/legal-text-format/archive/'
    
    files = [
        {
            'in': '260424 附判决┃上海高院发布2025年知识产权司法保护典型案例（15件）.md',
            'out': '20260425_120000_上海高院2025年知识产权司法保护典型案例/20260425_上海高院2025年知识产权司法保护典型案例_formatted.md',
            'court': '上海市高级人民法院',
            'url': 'http://mp.weixin.qq.com/s?__biz=MzUxMDAwNTI3OQ==&mid=2247532175&idx=2&sn=751cc17ca602a741d0907998de151fbe&chksm=f87a9b84ec2b4bc7b78b84fdbd4bf0ba3827e3eb63f8f9768c93aa60618863f60309595d8d24&scene=0#rd',
            'title': '上海高院发布2025年知识产权司法保护典型案例（15件）',
        },
        {
            'in': '260424 附判决┃天津高院发布2025年天津法院知识产权典型案例（7件）.md',
            'out': '20260425_120001_天津高院2025年天津法院知识产权典型案例/20260425_天津高院2025年天津法院知识产权典型案例_formatted.md',
            'court': '天津市高级人民法院',
            'url': 'http://mp.weixin.qq.com/s?__biz=MzUxMDAwNTI3OQ==&mid=2247532189&idx=3&sn=3a1b1ab7c375e156918800d365010de4&chksm=f8132c0da197ac9347ebc93310b701ec2fd60fc5d93cab64d9c641836e139c7845e97107bf74&scene=0#rd',
            'title': '天津高院发布2025年天津法院知识产权典型案例（7件）',
        },
        {
            'in': '260424 附判决┃青岛中院发布2025年青岛法院知识产权司法保护典型案例（10件）.md',
            'out': '20260425_120002_青岛中院2025年青岛法院知识产权司法保护典型案例/20260425_青岛中院2025年青岛法院知识产权司法保护典型案例_formatted.md',
            'court': '青岛市中级人民法院',
            'url': 'http://mp.weixin.qq.com/s?__biz=MzUxMDAwNTI3OQ==&mid=2247532204&idx=2&sn=e220a7465591667168de8d685ce05a8d&chksm=f8c9e4c174bd94ae03bbd21779674c01f5dd9d3ab12a5f6c71180eeed91873fce2ee30b7991d&scene=0#rd',
            'title': '青岛中院发布2025年青岛法院知识产权司法保护典型案例（10件）',
        },
        {
            'in': '260424 附判决┃湖南高院发布2025年知识产权司法保护状况及服务保障新质生产力发展典型案.md',
            'out': '20260425_120003_湖南高院2025年知识产权司法保护状况及服务保障新质生产力发展典型案例/20260425_湖南高院2025年知识产权司法保护状况及服务保障新质生产力发展典型案例_formatted.md',
            'court': '湖南省高级人民法院',
            'url': 'http://mp.weixin.qq.com/s?__biz=MzUxMDAwNTI3OQ==&mid=2247532189&idx=2&sn=2e4e073bed6c1690a7ede674cb29aec1&chksm=f8b9319c5f542f0b4ca89b8532273823caefe2ec8cf57cae69a39fc78430733517fa3c2ae1bf&scene=0#rd',
            'title': '湖南高院发布2025年知识产权司法保护状况及服务保障新质生产力发展典型案例',
        },
        {
            'in': '260424 附判决┃宁波中院发布2025年度宁波法院知识产权审判典型案例（10件）.md',
            'out': '20260425_120004_宁波中院2025年度宁波法院知识产权审判典型案例/20260425_宁波中院2025年度宁波法院知识产权审判典型案例_formatted.md',
            'court': '宁波市中级人民法院',
            'url': 'http://mp.weixin.qq.com/s?__biz=MzUxMDAwNTI3OQ==&mid=2247532189&idx=4&sn=a017ba462c773185997706d6d1bd8d5d&chksm=f85c4b3d874dc4d44897ad3cce8fa702f91cb63ec37b2c324217fe6c6e31bd678a408b0926ec&scene=0#rd',
            'title': '宁波中院发布2025年度宁波法院知识产权审判典型案例（10件）',
        },
        {
            'in': '260424 附判决┃江苏高院发布2025年服务保障科技创新和产业创新融合知产典型案例（10件.md',
            'out': '20260425_120005_江苏高院2025年服务保障科技创新和产业创新融合知产典型案例/20260425_江苏高院2025年服务保障科技创新和产业创新融合知产典型案例_formatted.md',
            'court': '江苏省高级人民法院',
            'url': 'http://mp.weixin.qq.com/s?__biz=MzUxMDAwNTI3OQ==&mid=2247532189&idx=1&sn=69c92887995f2e2d071a934d59a2be7e&chksm=f86160cc32719cb2c3e6d6e564503e2e31c5f59fd13a61e0a25560cc685ed293645966e7be25&scene=0#rd',
            'title': '江苏高院发布2025年服务保障科技创新和产业创新融合知产典型案例（10件）',
        },
        {
            'in': '260424 上海高院发布涉商业秘密保护典型案例（10件）.md',
            'out': '20260425_120006_上海高院涉商业秘密保护典型案例/20260425_上海高院涉商业秘密保护典型案例_formatted.md',
            'court': '上海市高级人民法院',
            'url': 'http://mp.weixin.qq.com/s?__biz=MzUxMDAwNTI3OQ==&mid=2247532175&idx=1&sn=123ffe43ea091b75c2b3fb633a3e433a&chksm=f81826aa74c0128a9fac0c4918dd2db3b9ea0b6403074b909ee91f132735bd72f2f6813c5ef8&scene=0#rd',
            'title': '上海高院发布涉商业秘密保护典型案例（10件）',
        },
        {
            'in': '260424 附判决┃南京中院发布2025年南京法院知识产权十大案例.md',
            'out': '20260425_120007_南京中院2025年南京法院知识产权十大案例/20260425_南京中院2025年南京法院知识产权十大案例_formatted.md',
            'court': '南京市中级人民法院',
            'url': 'http://mp.weixin.qq.com/s?__biz=MzUxMDAwNTI3OQ==&mid=2247532204&idx=1&sn=7127f2c0695db3e924509b24a0a2cb27&chksm=f87c7d06daaa5b24f5bc37b84f6fc30ec6c896dfa80a05772a9ad343096f36d00b81b29b5d8f&scene=0#rd',
            'title': '南京中院发布2025年南京法院知识产权十大案例',
        },
        {
            'in': '260423 4·26特辑 _ 上海法院发布知识产权审判白皮书和典型案例.md',
            'out': '20260425_120008_上海法院知识产权审判白皮书和典型案例/20260425_上海法院知识产权审判白皮书和典型案例_formatted.md',
            'court': '上海市高级人民法院',
            'url': 'http://mp.weixin.qq.com/s?__biz=MjM5NzU5ODEzNw==&mid=2665453880&idx=1&sn=44354253167edd6ec8268facdae0adba&chksm=bcd59bf527ccf9d451cb566915572414243a1c12c9cfc2c49a785cc02bfca32061912c70a4fd&scene=0#rd',
            'title': '上海法院发布知识产权审判白皮书和典型案例',
        },
    ]
    
    for f in files:
        inp = base_in + f['in']
        outp = base_out + f['out']
        try:
            process_file(inp, outp, f['court'], f['url'], f['title'])
        except Exception as e:
            print(f"Error processing {f['in']}: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    main()
