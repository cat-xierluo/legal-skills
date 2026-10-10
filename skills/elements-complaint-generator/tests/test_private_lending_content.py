#!/usr/bin/env python3
"""09 原始 OOXML 回归：逐问题行检查内容，结构门禁不等于法律审核。"""
from __future__ import annotations
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import fill_template as ft
import layout_gate
TEMPLATE = ROOT / 'templates/09-民间借贷纠纷-民事起诉状'


def fixture():
    return {
        '当事人': {
            role: {'主体类型': '自然人', '姓名': f'合成{role}', '性别': gender,
                   '出生日期': '1990-01-02', '民族': f'合成{role}民族',
                   '工作单位': f'合成{role}单位', '职务': f'合成{role}职务',
                   '联系电话': f'合成{role}电话', '住所地': f'合成{role}地址',
                   '经常居住地': f'合成{role}居住地', '证件类型': '合成测试证件',
                   '证件号码': f'合成{role}编号'}
            for role, gender in [('原告','男'), ('被告','女')]
        },
        '诉讼请求': {'本金': {'截至日期': '2026-09-30', '尚欠金额': '10000.00'},
            '利息': {'截至日期': '2026-09-30', '尚欠利息': '120.00',
                     '计算方式': '合成利息说明', '请求至实际清偿之日': False},
            '是否要求提前还款或解除合同': {'勾选': False, '提前还款_加速到期': False, '解除合同': False},
            '是否主张担保权利': {'勾选': False}, '是否主张实现债权的费用': {'勾选': False},
            '是否主张诉讼费用': False, '其他请求': '合成其他请求', '标的总额': '10120.00'},
        '约定管辖和诉前保全': {'有无仲裁_法院管辖约定': False, '是否已经诉前保全': False},
        '事实与理由': {
            '合同签订情况_名称_编号_签订时间_地点': '仅供自动测试的合成合同情况',
            '借款金额': {'提供方式': '转账'}, '借款期限': {'是否到期': False},
            '借款提供时间': '2026-01-02', '借款提供金额': '10000.00',
            '还款方式': '合成自定义还款安排', '是否存在逾期还款': {'勾选': False},
            '是否签订物的担保_抵押_质押_合同': {'勾选': False},
            '是否最高额担保_抵押_质押': False,
            '是否办理抵押_质押_登记': {'勾选': False, '正式登记': False, '预告登记': False},
            '是否签订保证合同': {'勾选': True, '签订时间': '2026-01-01',
                '保证人': '合成保证人', '主要内容': '合成保证说明', '保证方式': '连带责任保证'},
            '其他担保方式': {'勾选': False}, '其他需要说明的内容': '合成补充说明',
            '证据清单': '仅供自动测试的合成证据目录'},
        '具状人_签字_盖章': '合成原告（待签字）', '具状日期': '2026-09-30',
    }


def document(elements):
    doc = ft.DocParts(ft.load_text_parts(TEMPLATE))
    result = ft.apply_rules(doc, ft.build_rules_02_private_lending(TEMPLATE, elements), elements)
    return doc, result


def row(doc, label):
    scoped = ft._lending_answer_doc(doc, label)
    return ''.join(p.text for p in ft.iter_paragraphs(scoped))


class RealTemplateContent(unittest.TestCase):
    def assert_clean(self, result):
        self.assertFalse([x for x in result['details'] if x[0] == 'error'], result)
        self.assertFalse(result['unresolved_inputs'], result)

    def test_actual_template_fields_and_unmodified_labels(self):
        data = fixture()
        data['当事人']['委托诉讼代理人'] = [{'主体类型': '自然人', '是否委托': True, '姓名': '合成代理人',
            '单位': '合成代理单位', '职务': '合成代理职务', '联系电话': '合成代理电话', '代理权限': '特别授权'}]
        doc, result = document(data)
        self.assert_clean(result)
        for role in ('原告', '被告'):
            text = row(doc, f'{role}（自然人）')
            for key, value in data['当事人'][role].items():
                if key not in ('主体类型', '性别', '出生日期'): self.assertIn(value, text)
            self.assertIn('1990年1月2日', text)
            self.assertNotIn('合成代理', text)
            self.assertNotIn('合成原告' if role == '被告' else '合成被告', text)
        self.assertIn('女☑', row(doc, '被告（自然人）'))
        agent = row(doc, '委托诉讼代理人')
        for value in ('合成代理人', '合成代理单位', '合成代理职务', '合成代理电话', '特别授权☑', '有☑'): self.assertIn(value, agent)
        self.assertNotIn('合成被告', agent)
        principal = row(doc, '1. 本金')
        self.assertEqual(principal.count('人民币，下同；如外币需特别注明'), 1)
        self.assertIn('截至2026年9月30日止，尚欠本金10000.00', principal)
        interest = row(doc, '2. 利息')
        for value in ('截至2026年9月30日止，尚欠利息120.00', '元；', '是□', '否☑'): self.assertIn(value, interest)
        self.assertIn('2026年1月2日，10000.00元', row(doc, '6. 借款提供时间'))
        self.assertIn('现金□    转账☑', row(doc, '3. 借款金额'))
        self.assertIn('一般保证□    连带责任保证☑', row(doc, '14. 是否签订保证合同'))
        self.assertIn('签订时间：2026年1月1日保证人：合成保证人', row(doc, '14. 是否签订保证合同'))
        self.assertIn('其他：合成自定义还款安排', row(doc, '7. 还款方式'))
        for label, value in [('7. 其他请求','合成其他请求'),('8. 标的总额','10120.00'),
            ('1. 合同签订情况（名称、 编号、签订时间、地点   等）','仅供自动测试的合成合同情况'),
            ('16. 其他需要说明的内容 （可另附页）','合成补充说明'),('18. 证据清单（可另附 页）','仅供自动测试的合成证据目录')]:
            self.assertIn(value, row(doc,label))
        original = ft.load_text_parts(TEMPLATE)['word/document.xml']
        def labels(tree):
            return [''.join(t.text or '' for t in cells[0].iter(ft.Wt)) for tr in tree.iter(f'{{{ft.W_NS}}}tr')
                    if len(cells := tr.findall(f'{{{ft.W_NS}}}tc')) >= 2]
        self.assertEqual(labels(original), labels(doc.parts['word/document.xml']))

    def test_false_yes_and_enum_variants_are_not_truthiness(self):
        data = fixture()
        for value, option in [(False,'否☑'),(True,'是☑')]:
            data['诉讼请求']['是否主张诉讼费用'] = value
            data['诉讼请求']['利息']['请求至实际清偿之日'] = value
            doc,result = document(data); self.assert_clean(result)
            self.assertIn(option,row(doc,'6. 是否主张诉讼费用'))
            self.assertIn(option,row(doc,'2. 利息'))
        for value in ('现金','转账','其他'):
            data['事实与理由']['借款金额']['提供方式'] = value
            doc,result=document(data); self.assert_clean(result)
            self.assertIn(value+'☑' if value!='其他' else '其他：待补充具体方式',row(doc,'3. 借款金额'))
        data['事实与理由']['是否签订保证合同']['保证方式']='一般保证'
        doc,result=document(data); self.assert_clean(result)
        self.assertIn('一般保证☑',row(doc,'14. 是否签订保证合同'))
        self.assertIn('连带责任保证□',row(doc,'14. 是否签订保证合同'))

    def test_bad_shapes_enums_and_unhandled_paths_fail_closed(self):
        changes = [lambda d: d['当事人'].update(原告=[{'姓名':'合成原告'}]),
            lambda d: d['当事人']['原告'].update(主体类型='法人'),
            lambda d: d['当事人'].update(委托诉讼代理人=[{},{}]),
            lambda d: d['当事人'].update(第三人={'姓名':'合成第三人'}),
            lambda d: d['诉讼请求'].update(是否主张诉讼费用='false'),
            lambda d: d['诉讼请求'].update(是否主张诉讼费用=0),
            lambda d: d['事实与理由']['借款金额'].update(提供方式='错误枚举'),
            lambda d: d['事实与理由']['是否签订保证合同'].update(保证方式='错误保证'),
            lambda d: d['诉讼请求'].update(其他={'勾选':True})]
        for change in changes:
            data=fixture(); change(data)
            _,result=document(data)
            self.assertTrue(any(x[0]=='error' for x in result['details']),result)

    def test_missing_row_cannot_silently_pass_even_for_false(self):
        data=fixture(); doc=ft.DocParts(ft.load_text_parts(TEMPLATE))
        for p in ft.iter_paragraphs(doc):
            if p.text == '6. 是否主张诉讼费用': p.text='模板问题行已改变'
        result=ft.apply_rules(doc,ft.build_rules_02_private_lending(),data)
        self.assertTrue(any(x[0]=='error' and '是否主张诉讼费用' in x[1] for x in result['details']))

    def test_drifted_date_blank_does_not_count_as_consumed(self):
        data=fixture();doc=ft.DocParts(ft.load_text_parts(TEMPLATE))
        scoped=ft._lending_answer_doc(doc,'原告（自然人）')
        for p in ft.iter_paragraphs(scoped):
            if '出生日期：' in p.text:
                ft.replace_in_paragraph(p,'出生日期：','出生日期：unexpected')
        result=ft.apply_rules(doc,ft.build_rules_02_private_lending(),data)
        self.assertTrue(any(status=='error' and '未实际写入' in name and '出生日期' in name
                            for status,name in result['details']))

    def test_production_longtext_fixture_obeys_09_contract(self):
        from smoke_render_longtext import build_stress_elements
        data,paths=build_stress_elements(TEMPLATE)
        self.assertTrue(paths)
        doc,result=document(data);self.assert_clean(result)
        self.assertNotIn('法人1',data['当事人'])

    def test_signature_text_cannot_steal_date_anchor(self):
        name='合成署名（日期：由本人确认）'
        doc,result=document({'具状人_签字_盖章':name,'具状日期':'2026-09-30'});self.assert_clean(result)
        texts=[p.text for p in ft.iter_paragraphs(doc)]
        self.assertIn('具状人（签字、盖章）：'+name+' 日期：2026年9月30日',texts)

    def test_name_cannot_introduce_a_second_gender_anchor(self):
        data={'当事人': {'原告': {'姓名':'合成姓名含性别：男□ 女□','性别':'女'}}}
        _,result=document(data)
        self.assertTrue(any(status=='error' and '锚点应唯一' in name and '性别' in name
                            for status,name in result['details']))

    def test_amount_only_retains_unit_once(self):
        for value in ('10000.00','10000.00元'):
            doc,result=document({'事实与理由': {'借款提供金额':value}}); self.assert_clean(result)
            self.assertEqual(row(doc,'6. 借款提供时间').count('元'),1)
            self.assertIn('10000.00元',row(doc,'6. 借款提供时间'))

    def test_narrative_labels_cannot_steal_other_rows(self):
        data=fixture()
        narrative='约定：合成条款；出借人：合成说明；合同约定：仅为测试；具状人（签字、盖章）：不是落款'
        data['事实与理由']['合同签订情况_名称_编号_签订时间_地点']=narrative
        data['事实与理由']['借款金额']['约定']='10000'
        data['事实与理由']['签订主体']={'出借人':'合成真实填入出借人'}
        data['事实与理由']['请求依据_合同约定']='合成真实填入合同约定'
        doc,result=document(data);self.assert_clean(result)
        self.assertEqual(row(doc,'1. 合同签订情况（名称、 编号、签订时间、地点   等）'),narrative)
        self.assertIn('约定：10000',row(doc,'3. 借款金额'))
        self.assertIn('合成真实填入出借人',row(doc,'2. 签订主体'))
        self.assertIn('合成真实填入合同约定',row(doc,'17. 请求依据'))

    def test_same_row_duplicate_anchor_fails_instead_of_changing_narrative(self):
        data={'事实与理由': {'借款金额': {'约定':'合成叙述含实际提供：标签','实际提供':'10000'}}}
        _,result=document(data)
        self.assertTrue(any(status=='error' and '锚点应唯一' in name for status,name in result['details']))

    def test_mediation_benefits_without_summary_and_invalid_enums(self):
        values=['不了解','了解','不了解','了解','不了解']
        data={'对纠纷解决方式的意愿': {'是否了解先行调解好处':values}}
        doc,result=document(data);self.assert_clean(result)
        self.assertNotIn('☑',row(doc,'是否了解调解作为非诉讼纠纷解决方式，能及时、高效、低成本、不伤和气地解决纠纷'))
        scoped=ft._lending_answer_doc(doc,'是否了解先行调解解决纠纷的好处')
        selected=[p.text for p in ft.iter_paragraphs(scoped) if '☑' in p.text]
        self.assertEqual(len(selected),5)
        for text,value in zip(selected,values): self.assertIn(value+'☑',text)
        for bad in [{'对纠纷解决方式的意愿': {'是否了解调解':'错误'}},
                    {'对纠纷解决方式的意愿': {'是否考虑先行调解':'错误'}},
                    {'对纠纷解决方式的意愿': {'是否了解先行调解好处':['了解']*4}},
                    {'事实与理由': {'借款利率': {'单位':'错误'}}},
                    {'事实与理由': {'借款利率': {'单位':'年'}}}]:
            _,result=document(bad)
            self.assertTrue(any(status=='error' for status,_ in result['details']))

    def test_every_main_boolean_is_scoped_and_false_is_explicit(self):
        cases=[
            ('诉讼请求.利息.请求至实际清偿之日','2. 利息','是','否'),
            ('诉讼请求.是否要求提前还款或解除合同.勾选','3. 是否要求提前还款或 解除合同','是','否'),
            ('诉讼请求.是否主张担保权利.勾选','4. 是否主张担保权利','是','否'),
            ('诉讼请求.是否主张实现债权的费用.勾选','5. 是否主张实现债权的 费用','是','否'),
            ('诉讼请求.是否主张诉讼费用','6. 是否主张诉讼费用','是','否'),
            ('约定管辖和诉前保全.有无仲裁_法院管辖约定','1. 有无仲裁、法院管辖 约定','有','无'),
            ('约定管辖和诉前保全.是否已经诉前保全','2. 是否已经诉前保全','是','否'),
            ('事实与理由.借款期限.是否到期','4. 借款期限','是','否'),
            ('事实与理由.是否存在逾期还款.勾选','9. 是否存在逾期还款','是','否'),
            ('事实与理由.是否签订物的担保_抵押_质押_合同.勾选','10. 是否签订物的担保 （抵押、质押）合同','是','否'),
            ('事实与理由.是否最高额担保_抵押_质押','12. 是否最高额担保（抵 押、质押）','是','否'),
            ('事实与理由.是否办理抵押_质押_登记.勾选','13. 是否办理抵押、质押 登记','是','否'),
            ('事实与理由.是否签订保证合同.勾选','14. 是否签订保证合同','是','否'),
            ('事实与理由.其他担保方式.勾选','15. 其他担保方式','是','否'),
        ]
        for path,label,yes,no in cases:
            for value,chosen,other in [(True,yes,no),(False,no,yes)]:
                data={}; current=data; keys=path.split('.')
                for key in keys[:-1]: current=current.setdefault(key,{})
                current[keys[-1]]=value
                doc,result=document(data); self.assert_clean(result)
                text=row(doc,label)
                self.assertIn(chosen+'☑',text,(path,value));self.assertIn(other+'□',text,(path,value))
                self.assertEqual(sum(p.text.count('☑') for p in ft.iter_paragraphs(doc)),1,(path,value))
        for path,label in [
            ('诉讼请求.是否要求提前还款或解除合同.提前还款_加速到期','3. 是否要求提前还款或 解除合同'),
            ('诉讼请求.是否要求提前还款或解除合同.解除合同','3. 是否要求提前还款或 解除合同'),
            ('事实与理由.是否办理抵押_质押_登记.正式登记','13. 是否办理抵押、质押 登记'),
            ('事实与理由.是否办理抵押_质押_登记.预告登记','13. 是否办理抵押、质押 登记')]:
            data={}; current=data; keys=path.split('.')
            for key in keys[:-1]: current=current.setdefault(key,{})
            current[keys[-1]]=False
            doc,result=document(data); self.assert_clean(result)
            self.assertNotIn('☑',row(doc,label))


class RealCLI(unittest.TestCase):
    def test_real_docx_gate_repeated_output_and_failures_preserve_output(self):
        source_hashes={p.relative_to(TEMPLATE):hashlib.sha256(p.read_bytes()).hexdigest() for p in TEMPLATE.rglob('*') if p.is_file()}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); data=root/'elements.json'; out=root/'candidate.docx'
            data.write_text(json.dumps(fixture(),ensure_ascii=False))
            cmd=[sys.executable,'-s','-B',str(ROOT/'scripts/fill_template.py'),'--case-type','09-private-lending',
                 '--elements',str(data),'--output',str(out)]
            canonical=[]
            for _ in range(2):
                result=subprocess.run(cmd+['--layout-check','docx'],capture_output=True,text=True,timeout=180)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                with zipfile.ZipFile(out) as z: canonical.append({n:z.read(n) for n in z.namelist()})
                report=layout_gate.check(out,layout_gate.load_policy(ROOT/'config/layout-policy.json',TEMPLATE.name),rendered=False)
                self.assertEqual(report['status'],'DOCX_VERIFIED',report)
            self.assertEqual(canonical[0],canonical[1])
            previous=out.read_bytes()
            invalid=fixture();invalid['事实与理由']['借款金额']['提供方式']='错误枚举'
            data.write_text(json.dumps(invalid,ensure_ascii=False))
            result=subprocess.run(cmd+['--layout-check','docx'],capture_output=True,text=True,timeout=180)
            self.assertEqual(result.returncode,3,result.stdout+result.stderr);self.assertEqual(out.read_bytes(),previous)
            out.unlink()
            result=subprocess.run(cmd+['--layout-check','docx'],capture_output=True,text=True,timeout=180)
            self.assertEqual(result.returncode,3,result.stdout+result.stderr);self.assertFalse(out.exists())
            out.write_bytes(previous)
            # Anchor survives but blank shape drifted: shared helper's True must not publish.
            templates=root/'templates';copied=templates/TEMPLATE.name
            shutil.copytree(TEMPLATE,copied)
            parts=ft.load_text_parts(copied);doc=ft.DocParts(parts)
            for p in ft.iter_paragraphs(ft._lending_answer_doc(doc,'原告（自然人）')):
                if '出生日期：' in p.text:
                    ft.replace_in_paragraph(p,'出生日期：','出生日期：unexpected')
            ft.save_text_parts(copied,parts)
            data.write_text(json.dumps(fixture(),ensure_ascii=False))
            drift_cmd=cmd+['--layout-check','docx','--templates-dir',str(templates)]
            result=subprocess.run(drift_cmd,capture_output=True,text=True,timeout=180)
            self.assertEqual(result.returncode,3,result.stdout+result.stderr);self.assertEqual(out.read_bytes(),previous)
            out.unlink()
            result=subprocess.run(drift_cmd,capture_output=True,text=True,timeout=180)
            self.assertEqual(result.returncode,3,result.stdout+result.stderr);self.assertFalse(out.exists())
            out.write_bytes(previous)
            # Unknown nonempty input is rejected by the unchanged global gate.
            data.write_text(json.dumps({'未知字段':'合成'},ensure_ascii=False))
            result=subprocess.run(cmd+['--layout-check','docx'],capture_output=True,text=True,timeout=180)
            self.assertEqual(result.returncode,6);self.assertEqual(out.read_bytes(),previous)
            # Current environment may lack an official renderer: default must never fall back.
            data.write_text(json.dumps(fixture(),ensure_ascii=False))
            found=layout_gate._find_soffice()
            if layout_gate._renderer_kind(layout_gate._soffice_version(found or ''))!='official':
                result=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
                self.assertEqual(result.returncode,5,result.stdout+result.stderr);self.assertEqual(out.read_bytes(),previous)
        self.assertEqual(source_hashes,{p.relative_to(TEMPLATE):hashlib.sha256(p.read_bytes()).hexdigest() for p in TEMPLATE.rglob('*') if p.is_file()})

if __name__ == '__main__': unittest.main()
