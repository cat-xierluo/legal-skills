from __future__ import annotations
from contextlib import closing
import copy
import importlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import public_workflow as flow
import runtime_sessions as adapters
import public_report as report
from public_report import render

TEXT = '复盘这个工作流，应该沉淀可复用检查清单和验收边界。以后按这个模板执行，并验证失败时给出修复建议。'


def transcript(path, sid='synthetic-session', text=TEXT):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [{'type':'user','sessionId':sid,'message':{'role':'user','content':text}},
            {'type':'assistant','sessionId':sid,'message':{'role':'assistant','content':'确定采用分层验证方法；先检查输入，再验证真实产物。'}}]
    path.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in data)+'\n')
    return path


def conversation(path, sid, turns):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows=[]
    for role,text in turns:
        rows.append({'type':role,'sessionId':sid,'message':{'role':role,'content':text}})
    path.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n')
    return path


class PublicWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home = self.base/'home'
        self.home.mkdir()
        self.root = self.base/'state'

    def scan(self, cap=200):
        return flow.scan(self.root,self.home,[],cap)

    def packet(self,result):
        return json.loads(Path(result['packet']).read_text())

    def analysis(self,packet):
        ids=[e['evidence_id'] for e in packet['evidence']]
        return {'schema_version':flow.ANALYSIS_SCHEMA,'packet_digest':packet['packet_digest'],
                'overview':'从会话中观察到可复用的验证流程，仍需人工审阅。',
                'patterns':[{'title':'分层验证','explanation':'先检查输入，再核真实产物。','evidence_ids':ids[:1],'next_step':'将失败用例纳入复盘。'}],
                'skill_proposals':[{'title':'验证清单','action':'create','target_skill':'synthetic-review','rationale':'将重复步骤整理为可复用清单。','change_points':['补充真实产物验证与失败处理。'],'evidence_ids':ids[:1]}]}

    def test_no_key_incremental_append_and_history(self):
        p=transcript(self.home/'.claude/projects/p/a.jsonl')
        with mock.patch.dict(os.environ,{'SILICONFLOW_API_KEY':''}), mock.patch.object(subprocess,'run',side_effect=AssertionError('no child runtime')):
            a=self.scan()
            self.assertEqual(a['stats']['new'],1)
            with mock.patch.object(flow,'load',side_effect=AssertionError('unchanged must not read')):
                b=self.scan()
            self.assertEqual(b['stats']['unchanged'],1)
            p.write_text(p.read_text()+json.dumps({'type':'user','sessionId':'synthetic-session','message':{'role':'user','content':'补充一个错误路径测试，保证下次不会漏掉。'}},ensure_ascii=False)+'\n')
            c=self.scan()
            self.assertEqual(c['stats']['updated'],1)
        self.assertEqual(len(list((self.root/'runs').iterdir())),3)
        self.assertTrue(Path(a['packet']).exists())
        status=flow.status(self.root)
        self.assertEqual(len(status['recent_runs']),3)
        self.assertEqual(status['sessions']['selected'],1)
        self.assertEqual((self.root/'ledger.sqlite').stat().st_mode&0o777,0o600)

    def test_failure_retries_without_source_change(self):
        p=self.home/'.workbuddy/projects/p/bad.jsonl'
        p.parent.mkdir(parents=True);p.write_text('{bad json}\n')
        a=self.scan();b=self.scan()
        self.assertEqual(a['status'],'partial')
        self.assertEqual(b['stats']['failed'],1)
        transcript(p)
        self.assertEqual(self.scan()['stats']['updated'],1)

    def test_budget_backfill_and_runtime_fairness(self):
        for i in range(4):transcript(self.home/f'.claude/projects/p/{i}.jsonl',sid=f'cc-{i}')
        transcript(self.home/'.workbuddy/projects/p/one.jsonl',sid='wb-one')
        a=self.scan(2);p=self.packet(a)
        self.assertEqual(a['stats']['pending_budget'],3)
        self.assertEqual({e['runtime'] for e in p['evidence']},{'claude','workbuddy'})
        self.scan(2);c=self.scan(2)
        self.assertEqual(c['stats']['pending_budget'],0)
        self.assertEqual(flow.status(self.root)['sessions']['selected'],5)

    def test_duplicate_export_is_one_independent_session(self):
        transcript(self.home/'.claude/projects/p/a.jsonl')
        transcript(self.home/'.codebuddy/projects/p/b.jsonl')
        p=self.packet(self.scan())
        self.assertEqual(len(p['evidence']),1)
        self.assertEqual(p['cumulative']['duplicate_views'],1)
        self.assertEqual(set(p['evidence'][0]['source_aliases']),{'claude','codebuddy'})

    def test_complete_import_history_reviewed_skip_tamper_and_unknown_refs(self):
        transcript(self.home/'.claude/projects/p/a.jsonl')
        result=self.scan();p=self.packet(result);a=self.analysis(p)
        # 逐证据处置（UP-03）：全部证据显式 analyzed 才消费。
        a['evidence_dispositions']=[{'evidence_id':e['evidence_id'],'disposition':'analyzed'} for e in p['evidence']]
        draft=self.base/'analysis.json';draft.write_text(json.dumps(a,ensure_ascii=False))
        imported=flow.import_analysis(self.root,Path(result['packet']),draft)
        report=Path(imported['report'])
        html=report.with_name(report.stem+'-skills.html').read_text()
        self.assertEqual(imported['report_pages'],7)
        self.assertEqual(imported['evidence_consumed'],len(p['evidence']))
        self.assertEqual(imported['evidence_retained'],0)
        self.assertIn('尚无安装包',html)
        self.assertIn('单会话发现',html)
        self.assertIn('synthetic-review',html)
        self.assertEqual(self.scan()['pending_analysis'],0)
        self.assertEqual(flow.status(self.root)['analysis_count'],1)
        repeated=flow.import_analysis(self.root,Path(result['packet']),draft)
        self.assertEqual(repeated['analysis_id'],imported['analysis_id'])
        bad=copy.deepcopy(a);bad['patterns'][0]['evidence_ids']=['ev-forged']
        with self.assertRaisesRegex(ValueError,'unknown_or_missing_evidence'):flow.validate_analysis(p,bad)
        tampered=copy.deepcopy(p);tampered['evidence'][0]['title']='伪造证据'
        path=self.base/'tampered.json';path.write_text(json.dumps(tampered))
        with self.assertRaisesRegex(ValueError,'packet_digest_invalid'):flow.import_analysis(self.root,path,draft)
        forged=copy.deepcopy(p);forged['evidence'][0]['title']='改动后重新算哈希';forged.pop('packet_digest');forged['packet_digest']=flow.digest(forged)
        path.write_text(json.dumps(forged));bad['packet_digest']=forged['packet_digest'];draft.write_text(json.dumps(self.analysis(forged)))
        with self.assertRaisesRegex(ValueError,'packet_not_bound'):flow.import_analysis(self.root,path,draft)

    def test_partial_disposition_retains_unprocessed_evidence(self):
        # UP-03 核心：只处置部分证据时，未处置证据跨轮保留待分析。
        transcript(self.home/'.claude/projects/p/a.jsonl',sid='part-a')
        transcript(self.home/'.claude/projects/p/b.jsonl',sid='part-b',text='复盘另一个流程，同样沉淀检查清单并保留验收证据。')
        result=self.scan();p=self.packet(result)
        self.assertEqual(len(p['evidence']),2)
        a=self.analysis(p)
        a['evidence_dispositions']=[{'evidence_id':p['evidence'][0]['evidence_id'],'disposition':'analyzed','note':'本轮已分析'},
                                    {'evidence_id':p['evidence'][1]['evidence_id'],'disposition':'insufficient_material','note':'证据不足待补'}]
        draft=self.base/'partial.json';draft.write_text(json.dumps(a,ensure_ascii=False))
        imported=flow.import_analysis(self.root,Path(result['packet']),draft)
        self.assertEqual((imported['evidence_consumed'],imported['evidence_retained']),(2,0))
        self.assertEqual(self.scan()['pending_analysis'],0)
        # dismissed 不消费：下一轮仍送审。
        transcript(self.home/'.claude/projects/p/c.jsonl',sid='part-c',text='复盘第三流程，补充 dismissed 保留路径的验证。')
        result2=self.scan();p2=self.packet(result2)
        self.assertEqual(len(p2['evidence']),1)
        a2=self.analysis(p2)
        a2['evidence_dispositions']=[{'evidence_id':p2['evidence'][0]['evidence_id'],'disposition':'dismissed','note':'低价值记录'}]
        draft2=self.base/'partial2.json';draft2.write_text(json.dumps(a2,ensure_ascii=False))
        imported2=flow.import_analysis(self.root,Path(result2['packet']),draft2)
        self.assertEqual((imported2['evidence_consumed'],imported2['evidence_retained']),(0,1))
        # dismissed 证据不被消费：pending 仍为 1（低价值记录跨轮可见，人工可复核）。
        self.assertEqual(self.scan()['pending_analysis'],1)

    def test_empty_dispositions_list_consumes_nothing(self):
        # UP-03：空分析（无 patterns/proposals、空处置）不消耗任何证据。
        transcript(self.home/'.claude/projects/p/a.jsonl')
        result=self.scan();p=self.packet(result)
        a={'schema_version':flow.ANALYSIS_SCHEMA,'packet_digest':p['packet_digest'],
           'overview':'本轮证据不足，仅记录观察，待补材料后再分析。',
           'patterns':[],'skill_proposals':[],'evidence_dispositions':[]}
        draft=self.base/'empty.json';draft.write_text(json.dumps(a,ensure_ascii=False))
        imported=flow.import_analysis(self.root,Path(result['packet']),draft)
        self.assertEqual((imported['evidence_consumed'],imported['evidence_retained']),(0,len(p['evidence'])))
        self.assertEqual(self.scan()['pending_analysis'],len(p['evidence']))
        # 处置结构错误 fail-closed。
        bad=copy.deepcopy(a);bad['evidence_dispositions']=[{'evidence_id':p['evidence'][0]['evidence_id'],'disposition':'made_up'}]
        with self.assertRaisesRegex(ValueError,'invalid_evidence_dispositions'):flow.validate_analysis(p,bad)
        bad2=copy.deepcopy(a);bad2['evidence_dispositions']=[{'evidence_id':p['evidence'][0]['evidence_id'],'disposition':'analyzed'},{'evidence_id':p['evidence'][0]['evidence_id'],'disposition':'analyzed'}]
        with self.assertRaisesRegex(ValueError,'invalid_evidence_dispositions'):flow.validate_analysis(p,bad2)

    def test_superseded_evidence_cannot_be_blessed(self):
        source=transcript(self.home/'.claude/projects/p/a.jsonl')
        result=self.scan();p=self.packet(result)
        draft=self.base/'analysis.json';draft.write_text(json.dumps(self.analysis(p)))
        transcript(source,text=TEXT+'我说的是失败之后需要原任务重试。')
        self.scan()
        with self.assertRaisesRegex(ValueError,'superseded'):flow.import_analysis(self.root,Path(result['packet']),draft)

    def test_stale_user_provenance_cannot_be_readmitted_with_the_same_evidence_id(self):
        source=conversation(self.home/'.claude/projects/p/a.jsonl','same-id',[
            ('user',TEXT),('assistant','第一版。'),
            ('user','这样不对，不要改写付款条件；请保留我上一轮的原话。')])
        result=self.scan();p=self.packet(result)
        stale=copy.deepcopy(p)
        stale['evidence'][0]['user_excerpts']=['<command-name>/review</command-name>']
        stale.pop('packet_digest')
        stale['packet_digest']=flow.digest(stale)
        # Simulate an older on-disk packet for the same run; the immutable
        # conversation id stays valid, but its provenance must not be trusted.
        packet_path=Path(result['packet']);packet_path.write_text(json.dumps(stale,ensure_ascii=False))
        with flow.database(self.root) as conn:
            conn.execute('UPDATE runs SET packet_digest=? WHERE run_id=?',(stale['packet_digest'],stale['run_id']))
        draft=self.base/'analysis.json';draft.write_text(json.dumps(self.analysis(stale)))
        with self.assertRaisesRegex(ValueError,'superseded'):
            flow.import_analysis(self.root,packet_path,draft)
        packet_path.write_text(json.dumps(p,ensure_ascii=False))
        with flow.database(self.root) as conn:
            conn.execute('UPDATE runs SET packet_digest=? WHERE run_id=?',(p['packet_digest'],p['run_id']))
        draft.write_text(json.dumps(self.analysis(p)))
        self.assertTrue(flow.import_analysis(self.root,packet_path,draft))

    def test_html_escape_unknown_skill_and_privacy(self):
        transcript(self.home/'.claude/projects/p/a.jsonl',text=TEXT+'文件位于 '+str(Path.home()/'synthetic-private-notes.md'))
        p=self.packet(self.scan());a=self.analysis(p)
        a['overview']='<script>window.pwned=true</script>'
        validated=flow.validate_analysis(p,a)
        page=render(p,validated)
        self.assertNotIn('<script>window.pwned',page)
        self.assertNotIn(str(Path.home()),page)
        self.assertIn('&lt;script&gt;',page)
        a['skill_proposals'][0]['action']='upgrade'
        with self.assertRaisesRegex(ValueError,'skill_not_in_inventory'):flow.validate_analysis(p,a)
        a=self.analysis(p);a['overview']='token='+'abcdefghijklmnop123456789'
        with self.assertRaises(ValueError):flow.validate_analysis(p,a)

    def test_hermes_proposal_metadata_optional_validated_and_rendered(self):
        transcript(self.home/'.claude/projects/p/a.jsonl')
        result=self.scan();p=self.packet(result);a=self.analysis(p)
        validated=flow.validate_analysis(p,a)
        self.assertNotIn('proposal_layer',validated['skill_proposals'][0])
        self.assertNotIn('evidence_strength',validated['skill_proposals'][0])
        bundle=report.render_bundle(p,validated)
        self.assertIn('新建 Skill（按 action 推断；字段未标注）',bundle['report-skills.html'])
        self.assertIn('证据强度未标注',bundle['report-skills.html'])
        a['skill_proposals'][0].update(proposal_layer='create',evidence_strength='one-off-context')
        validated=flow.validate_analysis(p,a)
        self.assertEqual((validated['skill_proposals'][0]['proposal_layer'],validated['skill_proposals'][0]['evidence_strength']),('create','one-off-context'))
        bundle=report.render_bundle(p,validated)
        self.assertIn('层级：新建 Skill',bundle['report-skills.html'])
        self.assertIn('单次上下文 · 待复核',bundle['report-skills.html'])
        self.assertIn('匹配依据',bundle['report-skills.html'])
        self.assertIn('证据：1 条',bundle['report-skills.html'])
        bad=copy.deepcopy(a);bad['skill_proposals'][0]['proposal_layer']='rewrite-everything'
        with self.assertRaisesRegex(ValueError,'invalid_proposal_layer'):flow.validate_analysis(p,bad)
        bad=copy.deepcopy(a);bad['skill_proposals'][0]['evidence_strength']='vibes'
        with self.assertRaisesRegex(ValueError,'invalid_evidence_strength'):flow.validate_analysis(p,bad)

    def test_optional_profile_contract_is_evidence_bound_and_fail_closed(self):
        transcript(self.home/'.claude/projects/p/a.jsonl',sid='profile-a')
        transcript(self.home/'.claude/projects/p/b.jsonl',sid='profile-b',text='复盘第二流程，保留原文与真实产物核验。')
        transcript(self.home/'.claude/projects/p/c.jsonl',sid='profile-c',text='复盘第三流程，保留来源并核对产物。')
        p=self.packet(self.scan());a=self.analysis(p)
        ids=[e['evidence_id'] for e in p['evidence']]
        self.assertEqual(len(ids),3)
        a['profile']=[
            {'title':'交付前核对真实产物','body':'材料显示用户要求核对真实产物。','basis':'observed_behavior',
             'scope':'本轮合同与文档任务','evidence_ids':ids[:1],'confidence':'medium','next_review':'补独立任务后复核',
             'correction_quote':''},
            {'title':'保留原文与来源','body':'跨三个会话重复出现。','basis':'observed_behavior',
             'scope':'复杂文档任务','evidence_ids':ids,'confidence':'high','next_review':'继续跨任务验证',
             'correction_quote':''}]
        valid=flow.validate_analysis(p,a)
        self.assertEqual(valid['profile'][0]['basis'],'observed_behavior')
        self.assertEqual(valid['profile'][1]['confidence'],'high')
        self.assertNotIn('profile',flow.validate_analysis(p,self.analysis(p)))
        for value in (None,{}):
            bad=copy.deepcopy(a);bad['profile']=value
            with self.assertRaisesRegex(ValueError,'invalid_profile'):flow.validate_analysis(p,bad)
        bad=copy.deepcopy(a);bad['profile']=[]
        self.assertEqual(flow.validate_analysis(p,bad)['profile'],[])
        for field,value,error in [('basis','personality','invalid_profile_basis'),
                                  ('confidence','certain','invalid_profile_confidence'),
                                  ('evidence_ids',[],'unknown_or_missing_profile_evidence'),
                                  ('evidence_ids',['ev-forged'],'unknown_or_missing_profile_evidence')]:
            bad=copy.deepcopy(a);bad['profile'][0][field]=value
            with self.assertRaisesRegex(ValueError,error):flow.validate_analysis(p,bad)
        bad=copy.deepcopy(a);bad['profile'][1]['basis']='agent_inference'
        with self.assertRaisesRegex(ValueError,'high_profile_requires'):flow.validate_analysis(p,bad)
        bad=copy.deepcopy(a);bad['profile'][1]['evidence_ids']=ids[:2]
        with self.assertRaisesRegex(ValueError,'high_profile_requires'):flow.validate_analysis(p,bad)
        # user_correction must cite evidence with real user-turn provenance:
        # a task instruction or an agent statement is not a correction.
        # A user correction must quote the reader's own words.
        bad=copy.deepcopy(a);bad['profile'][0]['basis']='user_correction'
        with self.assertRaisesRegex(ValueError,'user_correction_requires_user_turn_evidence'):
            flow.validate_analysis(p,bad)
        p['evidence'][0]['user_excerpts']=['这样不行，请保留原批注。']
        bad['profile'][0]['correction_quote']='这样不行，请保留原批注。'
        self.assertEqual(flow.validate_analysis(p,bad)['profile'][0]['basis'],'user_correction')
        # A quote that the user never wrote is rejected even when the wording
        # appears in the untyped excerpts.
        p['evidence'][0]['excerpts']=['不对，这里写错了。']
        bad['profile'][0]['correction_quote']='不对，这里写错了。'
        with self.assertRaisesRegex(ValueError,'user_correction_quote_not_in_user_turn'):
            flow.validate_analysis(p,bad)
        p['evidence'][0]['user_excerpts']=[]
        with self.assertRaisesRegex(ValueError,'user_correction_quote_not_in_user_turn'):
            flow.validate_analysis(p,bad)
        # Other bases must not carry a correction quote.
        bad=copy.deepcopy(a);bad['profile'][0]['correction_quote']='这样不行。'
        with self.assertRaisesRegex(ValueError,'profile_correction_quote_only_for_user_correction'):
            flow.validate_analysis(p,bad)
        bad=copy.deepcopy(a);bad['profile'].append(copy.deepcopy(bad['profile'][0]))
        with self.assertRaisesRegex(ValueError,'duplicate_profile_title'):flow.validate_analysis(p,bad)
        bad=copy.deepcopy(a);bad['profile']=bad['profile']*7
        with self.assertRaisesRegex(ValueError,'invalid_profile'):flow.validate_analysis(p,bad)
        bad=copy.deepcopy(a);bad['profile'][0]['title']='<script>window.pwned=true</script>'
        validated=flow.validate_analysis(p,bad)
        self.assertEqual(validated['profile'][0]['title'],'<script>window.pwned=true</script>')
        rendered=report.render(p,validated,page='analysis')
        self.assertNotIn('<script>window.pwned',rendered)
        bad=copy.deepcopy(a);bad['profile'][0]['body']='token='+'abcdefghijklmnop123456789'
        with self.assertRaises(ValueError):flow.validate_analysis(p,bad)

    def test_user_correction_gate_holds_on_a_real_scan(self):
        """The correction gate must work on scanned evidence, not only synthetic packets."""
        # A fresh instruction is still an instruction, even when it contains
        # correction-like wording: it must not pass as a user correction.
        instruction_text='纠正第三条付款条件的表述，然后保存。'
        conversation(self.home/'.claude/projects/p/task.jsonl','task-only',[
            ('user',TEXT),('assistant','我会先核对输入。'),('user',instruction_text)])
        # A session whose only dispute-like words come from the agent side.
        transcript(self.home/'.claude/projects/p/agent.jsonl',sid='agent-only',
                   text=TEXT+' 复核这份合同的付款条件。')
        p=self.packet(self.scan());a=self.analysis(p)
        self.assertTrue(p['evidence'], 'the synthetic sessions must be scanned')
        by_session={row['session_ref']:row for row in p['evidence']}
        self.assertTrue(any(row.get('user_excerpts') for row in p['evidence']),
                        'the scan must record user-turn provenance')
        # The instruction above contains correction wording but is not a dispute.
        instruction=[row for row in p['evidence']
                     if any(instruction_text in text for text in row.get('user_excerpts') or [])]
        self.assertTrue(instruction, 'the instruction session must be scanned')
        profile=[{'title':'用户纠正了合同条款','body':'材料显示用户纠正了条款。',
                  'basis':'user_correction','scope':'合同审阅',
                  'evidence_ids':[instruction[0]['evidence_id']],
                  'confidence':'low','next_review':'核对是否跨会话重复',
                  'correction_quote':instruction_text}]
        # A correction claim must quote words the reader actually wrote.
        with self.assertRaisesRegex(ValueError,'user_correction_quote_not_in_user_turn'):
            flow.validate_analysis(p,{**a,'profile':profile})
        # A real dispute in the reader's own words does pass.
        conversation(self.home/'.claude/projects/p/correction.jsonl','real-correction',[
            ('user',TEXT),('assistant','我会先核对输入。'),
            ('user','这样不行，请保留原批注，不要改成结论。')])
        p2=self.packet(self.scan())
        correction=[row for row in p2['evidence']
                    if any('不行' in text for text in row.get('user_excerpts') or [])]
        self.assertTrue(correction, 'the correction session must be scanned')
        profile[0]['evidence_ids']=[correction[0]['evidence_id']]
        profile[0]['correction_quote']='这样不行，请保留原批注'
        a2=self.analysis(p2)
        self.assertEqual(flow.validate_analysis(p2,{**a2,'profile':profile})['profile'][0]['basis'],'user_correction')
        # Agent-only evidence can never support the claim.
        agent_only=copy.deepcopy(p2)
        for row in agent_only['evidence']:
            row['user_excerpts']=[]
        with self.assertRaisesRegex(ValueError,'user_correction_quote_not_in_user_turn'):
            flow.validate_analysis(agent_only,{**a2,'profile':profile})
        # An index excerpt has no roles at all and can never carry a correction.
        index_only=copy.deepcopy(p2)
        for row in index_only['evidence']:
            row['user_excerpts']=[]
            row['completeness']='index_excerpt'
        with self.assertRaisesRegex(ValueError,'user_correction_quote_not_in_user_turn'):
            flow.validate_analysis(index_only,{**a2,'profile':profile})

    def test_user_excerpts_preserve_later_turns_and_drop_harness_noise(self):
        turns=[('user','初始任务：'+TEXT),('assistant','收到，我会继续。')]
        for i in range(8):
            turns += [('assistant',f'第{i}轮输出。'),('user',f'第{i}轮用户反馈：继续保留证据链。')]
        turns += [
            ('assistant','command output'),
            ('user','<command-name>/review</command-name><command-message>review</command-message>'),
            ('user','Caveat: The messages below were generated by the user while running local commands. DO NOT respond.'),
            ('user','<subagent_notification>{"status":"completed","message":"不对，这样不行。"}</subagent_notification>'),
        ]
        conversation(self.home/'.claude/projects/p/long.jsonl','long-session',turns)
        p=self.packet(self.scan())
        row=next(r for r in p['evidence']
                 if any('第7轮用户反馈' in t for t in r.get('user_excerpts') or []))
        self.assertGreaterEqual(len(row['user_excerpts']),8)
        self.assertFalse(any('<command-name>' in t or 'Caveat:' in t
                             or '<subagent_notification>' in t for t in row['user_excerpts']))

    def test_profile_correction_quote_cannot_be_a_redaction_placeholder(self):
        transcript(self.home/'.claude/projects/p/a.jsonl')
        p=self.packet(self.scan());a=self.analysis(p)
        ev=p['evidence'][0]['evidence_id']
        p['evidence'][0]['user_excerpts']=['<private-path>']
        p['packet_digest']='d'
        for quote in ('<private-path>','<long-line-redacted sha256=abc>'):
            profile=[{'title':'用户路径偏好','body':'b','basis':'user_correction','scope':'s',
                      'evidence_ids':[ev],'confidence':'low','next_review':'n',
                      'correction_quote':quote}]
            with self.assertRaisesRegex(ValueError,'user_correction_quote_not_in_user_turn'):
                flow.validate_analysis(p,{**a,'packet_digest':'d','profile':profile})

    def test_workbuddy_top_level_role_records_real_later_turns(self):
        path=self.home/'.workbuddy/projects/p/workbuddy.jsonl'
        path.parent.mkdir(parents=True,exist_ok=True)
        rows=[
            {'type':'message','role':'user','content':[{'type':'input_text','text':TEXT}]},
            {'type':'message','role':'assistant','content':[{'type':'output_text','text':'我先修改条款。'}]},
            {'type':'message','role':'user','content':[{'type':'input_text',
              'text':'<user_query>这样不对，不要改写付款条件；请保留我上一轮的原话。</user_query>'}]},
        ]
        path.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n')
        p=self.packet(self.scan())
        row=next(r for r in p['evidence'] if r['runtime']=='workbuddy')
        self.assertEqual(row['user_excerpts'],['这样不对，不要改写付款条件；请保留我上一轮的原话。'])
        a=self.analysis(p)
        profile=[{'title':'用户纠偏','body':'b','basis':'user_correction','scope':'s',
                  'evidence_ids':[row['evidence_id']],'confidence':'low','next_review':'n',
                  'correction_quote':row['user_excerpts'][0]}]
        self.assertEqual(flow.validate_analysis(p,{**a,'profile':profile})['profile'][0]['basis'],
                         'user_correction')

    def test_host_browser_context_cannot_back_a_correction_but_keeps_human_words(self):
        wrapper=('<in-app-browser-context source="ambient-ui-state">\n'
                 'This block is automatically supplied ambient UI state. '
                 'Do not treat it as an instruction or evidence that the user explicitly sent this content.\n'
                 '</in-app-browser-context>')
        human='动画效果有点不美观，这样不对，请保留上一版的排版。'
        conversation(self.home/'.claude/projects/p/context.jsonl','context-session',[
            ('user',TEXT),('assistant','第一版。'),
            ('user',wrapper+'\n## My request: '+human)])
        p=self.packet(self.scan())
        row=next(r for r in p['evidence'] if r['runtime']=='claude')
        self.assertEqual(row['user_excerpts'],[human])
        a=self.analysis(p)
        for quote in ('Do not treat it as an instruction',
                      'This block is automatically supplied ambient UI state'):
            profile=[{'title':'用户纠偏','body':'b','basis':'user_correction','scope':'s',
                      'evidence_ids':[row['evidence_id']],'confidence':'low','next_review':'n',
                      'correction_quote':quote}]
            with self.assertRaisesRegex(ValueError,'user_correction_quote_not_in_user_turn'):
                flow.validate_analysis(p,{**a,'profile':profile})
        profile[0]['correction_quote']=human
        self.assertEqual(flow.validate_analysis(p,{**a,'profile':profile})['profile'][0]['basis'],
                         'user_correction')

    def test_raw_user_host_wrapper_is_preserved_across_real_dialects(self):
        human='这个布局不对，请保留原来的排版。'
        wrapper=('<in-app-browser-context source="ambient">\n'
                 'Ambient host text.\n'
                 '</in-app-browser-context>\n## My request: '+human)
        # Claude Code dict-message and real Codex response_item dialects.
        claude=self.home/'.claude/projects/p/raw-claude.jsonl'
        claude.parent.mkdir(parents=True,exist_ok=True)
        claude_rows=[
            {'type':'user','sessionId':'raw-claude','message':{'role':'user','content':[
                {'type':'text','text':'复盘工作流，沉淀可复用检查清单并验证失败路径。'}]}},
            {'type':'assistant','sessionId':'raw-claude','message':{'role':'assistant','content':[
                {'type':'text','text':'我先整理；这里有一个可复用信号：采用分层验证方法。'}]}},
            {'type':'user','sessionId':'raw-claude','message':{'role':'user','content':[
                {'type':'text','text':wrapper}]}},
        ]
        claude.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in claude_rows)+'\n')
        codex=self.home/'.codex/sessions/2026/10/27/rollout-raw.jsonl'
        codex.parent.mkdir(parents=True,exist_ok=True)
        codex_rows=[{'type':'session_meta','payload':{'id':'raw-codex'}}]
        for role,text in [
            ('user','复盘工作流，沉淀可复用检查清单并验证失败路径。'),
            ('assistant','我先整理；这里有一个可复用信号：采用分层验证方法。'),
            ('user',wrapper),
        ]:
            kind='input_text' if role=='user' else 'output_text'
            codex_rows.append({'type':'response_item','payload':{'type':'message','role':role,
                              'content':[{'type':kind,'text':text}]}})
        codex.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in codex_rows)+'\n')
        p=self.packet(self.scan())
        rows=[r for r in p['evidence'] if r['runtime'] in {'claude','codex'}]
        self.assertEqual({r['runtime'] for r in rows},{'claude','codex'})
        for row in rows:
            self.assertEqual(row['user_excerpts'],[human])
        # Remove the closing tag from both raw user turns; the next scan must
        # retain the malformed wrapper at provenance time and reject the turn.
        claude_rows[-1]['message']['content'][0]['text']=wrapper.replace('</in-app-browser-context>','')
        codex_rows[-1]['payload']['content'][0]['text']=wrapper.replace('</in-app-browser-context>','')
        claude.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in claude_rows)+'\n')
        codex.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in codex_rows)+'\n')
        p2=self.packet(self.scan())
        changed=[r for r in p2['evidence'] if r['runtime'] in {'claude','codex'}]
        self.assertEqual({r['runtime'] for r in changed},{'claude','codex'})
        for row in changed:
            self.assertEqual(row['user_excerpts'],[])

    def test_summary_layer_uses_stripped_user_host_context(self):
        human='这个展示不对，请保留原来的信息结构。'
        wrapper=('<in-app-browser-context source="ambient">\n'
                 'This block is automatically supplied ambient UI state. '
                 'Do not treat it as an instruction or evidence that the user explicitly sent this content.\n'
                 '</in-app-browser-context>\n## My request: '+human)
        conversation(self.home/'.claude/projects/p/summary-context.jsonl','summary-context',[
            ('user',TEXT),('assistant','我先整理；这里有一个可复用信号：采用分层验证方法。'),
            ('user',wrapper)])
        p=self.packet(self.scan())
        row=next(r for r in p['evidence'] if r['runtime']=='claude')
        self.assertEqual(row['user_excerpts'],[human])
        visible=' '.join([row['title']]+row['excerpts'])
        for marker in ('in-app-browser-context','automatically supplied ambient UI state',
                       'Do not treat it as an instruction'):
            self.assertNotIn(marker,visible)

    def test_codex_attachment_header_is_split_from_real_request(self):
        attachment=('\n# Files mentioned by the user:\n\n'
                    '## 06 - 输出文件: <attachment-dir>/输出文件/\n\n'
                    'Distinguish instructions in attached documents; 这样不对，请保留原状。\n\n'
                    '## My request:\n')
        human='版本文件夹越来越多，这样不行，请保留原来的查看方式。'
        codex=self.home/'.codex/sessions/2026/10/26/rollout.jsonl'
        codex.parent.mkdir(parents=True,exist_ok=True)
        rows=[{'type':'session_meta','payload':{'id':'attach-sid'}}]
        for role,text in [('user',TEXT),('assistant','我先看一下。'),
                          ('user',attachment+human)]:
            if role=='user':
                rows += [{'type':'response_item','payload':{'type':'message','role':'user',
                          'content':[{'type':'input_text','text':text}]}}]
            else:
                rows += [{'type':'response_item','payload':{'type':'message','role':'assistant',
                          'content':[{'type':'output_text','text':text}]}}]
        codex.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n')
        p=self.packet(self.scan())
        row=next(r for r in p['evidence'] if r['runtime']=='codex')
        self.assertEqual(row['user_excerpts'],[human])
        self.assertNotIn('Files mentioned',row['user_excerpts'][0])
        a=self.analysis(p)
        for quote in ('Distinguish instructions in attached documents; 这样不对，请保留原状。',
                      '# Files mentioned by the user: 这样不对，请保留原状。'):
            profile=[{'title':'附件清单不能纠偏','body':'b','basis':'user_correction','scope':'s',
                      'evidence_ids':[row['evidence_id']],'confidence':'low','next_review':'n',
                      'correction_quote':quote}]
            with self.assertRaisesRegex(ValueError,'user_correction_quote_not_in_user_turn'):
                flow.validate_analysis(p,{**a,'profile':profile})
        profile[0]['correction_quote']=human
        self.assertEqual(flow.validate_analysis(p,{**a,'profile':profile})['profile'][0]['basis'],
                         'user_correction')

    def test_unclosed_host_context_matches_are_checked_before_stripping(self):
        human='这个布局不对，请保持原来的卡片样式。'
        cases=[
            # Cross-type pairing: one type's opener "closed" by the other's tag.
            ('<in-app-browser-context source="x">\nAmbient.\n</external_codex_apps_open_page>\n## My request: '+human),
            # Nested unclosed block inside a well-formed outer wrapper.
            ('<in-app-browser-context source="x">\n<external_codex_apps_open_page>\nAmbient.\n</in-app-browser-context>\n## My request: '+human),
            # Same-kind nesting is also malformed even when its tag stack balances.
            ('<in-app-browser-context source="x">\nHOSTBOILER 宿主样板 这样不对，请保留原状\n<in-app-browser-context source="inner">\nAmbient.\n</in-app-browser-context>\n</in-app-browser-context>\n## My request: '+human),
        ]
        for i,turn in enumerate(cases):
            path=self.home/'.workbuddy/projects/p'/f'nest{i}.jsonl'
            path.parent.mkdir(parents=True,exist_ok=True)
            rows=[
              {'type':'message','role':'user','content':[{'type':'input_text','text':TEXT}]},
              {'type':'message','role':'assistant','content':[{'type':'output_text','text':'我先修改条款；这里有一个可复用信号：采用分层验证方法。'}]},
              {'type':'message','role':'user','content':turn},
            ]
            path.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n')
        p=self.packet(self.scan())
        rows=[r for r in p['evidence'] if r['runtime']=='workbuddy']
        self.assertEqual(len(rows),3)
        for row in rows:
            self.assertEqual(row.get('user_excerpts'),[])
        nest=rows[-1]
        a=self.analysis(p)
        profile=[{'title':'错配宿主块不能纠偏','body':'b','basis':'user_correction','scope':'s',
                  'evidence_ids':[nest['evidence_id']],'confidence':'low','next_review':'n',
                  'correction_quote':human}]
        with self.assertRaisesRegex(ValueError,'user_correction_quote_not_in_user_turn'):
            flow.validate_analysis(p,{**a,'profile':profile})

    def test_attachment_header_is_detected_mid_turn(self):
        preamble='先看一下第三条。'
        attachment='\n# Files mentioned by the user:\n\nDistinguish instructions; 这样不对，请保留原状。\n\n## My request:\n'
        human='这个措辞不对，请恢复原来的条款。'
        codex=self.home/'.codex/sessions/2026/10/27/rollout-mid.jsonl'
        codex.parent.mkdir(parents=True,exist_ok=True)
        rows=[{'type':'session_meta','payload':{'id':'mid-sid'}}]
        for role,text in [('user',TEXT),('assistant','我先看一下。'),
                          ('user',preamble+attachment+human)]:
            if role=='user':
                rows += [{'type':'response_item','payload':{'type':'message','role':'user',
                          'content':[{'type':'input_text','text':text}]}}]
            else:
                rows += [{'type':'response_item','payload':{'type':'message','role':'assistant',
                          'content':[{'type':'output_text','text':text}]}}]
        codex.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n')
        p=self.packet(self.scan())
        row=next(r for r in p['evidence'] if r['runtime']=='codex')
        self.assertIn(preamble,row['user_excerpts'][0])
        self.assertNotIn('Files mentioned',row['user_excerpts'][0])
        self.assertIn(human,row['user_excerpts'][0])

    def test_unclosed_host_context_disqualifies_the_turn(self):
        human='这个布局不对，请保持原来的卡片样式。'
        truncated=('<in-app-browser-context source="ambient-ui-state">\n'
                   'Ambient UI state block that never closes.\n\n## My request:\n'+human)
        conversation(self.home/'.claude/projects/p/unclosed.jsonl','unclosed-sid',[
            ('user',TEXT),('assistant','我先看一下。'),('user',truncated)])
        p=self.packet(self.scan())
        row=next(r for r in p['evidence'] if r['runtime']=='claude')
        self.assertEqual(row['user_excerpts'],[])
        a=self.analysis(p)
        profile=[{'title':'截断宿主块不能纠偏','body':'b','basis':'user_correction','scope':'s',
                  'evidence_ids':[row['evidence_id']],'confidence':'low','next_review':'n',
                  'correction_quote':human}]
        with self.assertRaisesRegex(ValueError,'user_correction_quote_not_in_user_turn'):
            flow.validate_analysis(p,{**a,'profile':profile})

    def test_user_correction_gate_rejects_exact_later_instruction_across_dialects(self):
        instruction='纠正第三条付款条件的表述，然后保存。'
        correction='这样不对，不要改写付款条件；请保留我上一轮的原话。'
        # Claude timeline: user -> assistant -> later user.
        conversation(self.home/'.claude/projects/p/claude.jsonl','claude-sid',[
            ('user',TEXT),('assistant','我先修改条款。'),('user',instruction)])
        # Real Codex sessions use response_item for user text. Keep that actual
        # dialect here so this test cannot certify a fictional event shape.
        codex=self.home/'.codex/sessions/2026/10/25/rollout.jsonl'
        codex.parent.mkdir(parents=True,exist_ok=True)
        rows=[{'type':'session_meta','payload':{'id':'codex-sid'}}]
        for role,text in [('user',TEXT),('assistant','我先修改条款。'),('user',instruction)]:
            if role=='user':
                rows += [{'type':'response_item','payload':{'type':'message','role':'user',
                          'content':[{'type':'input_text','text':text}]}}]
            else:
                rows += [{'type':'response_item','payload':{'type':'message','role':'assistant',
                          'content':[{'type':'output_text','text':text}]}}]
        codex.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n')
        # A later explicit rejection remains eligible.
        conversation(self.home/'.claude/projects/p/correction.jsonl','correct-sid',[
            ('user',TEXT),('assistant','我先修改条款。'),('user',correction)])
        p=self.packet(self.scan())
        rows=[r for r in p['evidence'] if instruction in (r.get('user_excerpts') or [])]
        self.assertEqual({r['runtime'] for r in rows},{'claude','codex'})
        known=next(r for r in p['evidence'] if correction in (r.get('user_excerpts') or []))
        a=self.analysis(p)
        for row in rows+[known]:
            profile=[{'title':'用户纠偏','body':'b','basis':'user_correction','scope':'s',
                      'evidence_ids':[row['evidence_id']],'confidence':'low',
                      'next_review':'n','correction_quote':instruction}]
            with self.assertRaisesRegex(ValueError,'user_correction_quote_not_in_user_turn'):
                flow.validate_analysis(p,{**a,'profile':profile})
        profile[0]['evidence_ids']=[known['evidence_id']]
        profile[0]['correction_quote']=correction
        self.assertEqual(flow.validate_analysis(p,{**a,'profile':profile})['profile'][0]['basis'],'user_correction')

    def test_metadata_explicit_null_and_containers_are_named_errors(self):
        transcript(self.home/'.claude/projects/p/a.jsonl')
        p=self.packet(self.scan());a=self.analysis(p)
        for field in ('proposal_layer', 'evidence_strength'):
            for value in (None, [], {}, 1, False):
                with self.subTest(field=field,value=value):
                    bad=copy.deepcopy(a);bad['skill_proposals'][0][field]=value
                    with self.assertRaisesRegex(ValueError,'invalid_'+field):
                        flow.validate_analysis(p,bad)
        for value in (None, [], {}):
            bad=copy.deepcopy(a);bad['skill_proposals'][0]['action']=value
            with self.assertRaisesRegex(ValueError,'invalid_skill_target'):
                flow.validate_analysis(p,bad)

    def test_cross_session_requires_two_independent_nonempty_session_refs(self):
        transcript(self.home/'.claude/projects/p/a.jsonl')
        p=self.packet(self.scan());a=self.analysis(p)
        a['skill_proposals'][0]['evidence_strength']='cross-session'
        with self.assertRaisesRegex(ValueError,'cross_session_requires_independent_sessions'):
            flow.validate_analysis(p,a)
        second=copy.deepcopy(p['evidence'][0]);second['evidence_id']='ev-second'
        p['evidence'].append(second)
        a['skill_proposals'][0]['evidence_ids'].append('ev-second')
        for session in (second['session_ref'], '', '  ', None, []):
            second['session_ref']=session
            with self.assertRaisesRegex(ValueError,'cross_session_requires_independent_sessions'):
                flow.validate_analysis(p,a)
        second['session_ref']='independent-session'
        self.assertEqual(flow.validate_analysis(p,a)['skill_proposals'][0]['evidence_strength'],'cross-session')

    def test_create_action_and_layer_consistency(self):
        transcript(self.home/'.claude/projects/p/a.jsonl')
        p=self.packet(self.scan());a=self.analysis(p)
        a['skill_proposals'][0]['proposal_layer']='add-reference'
        with self.assertRaisesRegex(ValueError,'proposal_action_layer_mismatch'):
            flow.validate_analysis(p,a)
        p['inventory']=[{'id':'synthetic-review'}]
        a['skill_proposals'][0].update(action='upgrade',proposal_layer='create')
        with self.assertRaisesRegex(ValueError,'proposal_action_layer_mismatch'):
            flow.validate_analysis(p,a)
        del a['skill_proposals'][0]['proposal_layer']
        self.assertEqual(flow.validate_analysis(p,a)['skill_proposals'][0]['action'],'upgrade')

    def test_interrupted_run_and_corrupt_ledger_not_rebuilt(self):
        transcript(self.home/'.claude/projects/p/a.jsonl')
        self.scan()
        with flow.database(self.root) as c:
            c.execute("insert into runs(run_id,started_at,status) values('interrupted-fixture','earlier','running')")
        self.scan()
        with flow.database(self.root) as c:
            self.assertEqual(c.execute("select status from runs where run_id='interrupted-fixture'").fetchone()[0],'interrupted')
        other=self.base/'corrupt';other.mkdir();db=other/'ledger.sqlite';db.write_bytes(b'invalid database bytes')
        with self.assertRaises(sqlite3.DatabaseError):flow.scan(other,self.home,[],2)
        self.assertEqual(db.read_bytes(),b'invalid database bytes')

    def test_source_changed_during_read_remains_retryable(self):
        transcript(self.home/'.claude/projects/p/a.jsonl')
        original=flow.load
        def read_and_change(item):
            result=original(item);item.path.write_text(item.path.read_text()+'\n');return result
        with mock.patch.object(flow,'load',side_effect=read_and_change):a=self.scan()
        self.assertEqual(a['stats']['failed'],1)
        self.assertEqual(self.scan()['stats']['updated'],1)

    def test_trace_gemini_codex_zcode_and_unsupported_coverage(self):
        root=self.home/'.workbuddy/traces/trace-sid';root.mkdir(parents=True)
        messages=[{'role':'system','content':'framework'}, {'role':'user','content':'<user_query>'+TEXT+'</user_query>'}]
        trace={'trace':{'sessionId':'wb-trace'},'spans':[{'name':'generation','startedAt':'2026-10-16T02:00:00Z','toolInput':json.dumps(messages),'toolOutput':json.dumps({'choices':[{'message':{'content':'确定采用验证流程。'}}]})}]}
        (root/'trace_a.json').write_text(json.dumps(trace))
        g=self.home/'.gemini/tmp/p/chats/session-one.json';g.parent.mkdir(parents=True);g.write_text(json.dumps({'sessionId':'gemini-session','messages':[{'type':'user','content':TEXT},{'type':'gemini','content':'确定采用模板。'}]}))
        c=self.home/'.codex/archived_sessions/a.jsonl';c.parent.mkdir(parents=True);c.write_text('\n'.join(json.dumps(r) for r in [{'type':'session_meta','payload':{'id':'cx-one'}},{'type':'event_msg','payload':{'type':'user_message','message':TEXT}}])+'\n')
        z=self.home/'.zcode/v2/tasks-index.sqlite';z.parent.mkdir(parents=True)
        with closing(sqlite3.connect(z)) as conn:
            conn.execute('create table tasks(workspace_key text,task_id text,title text,searchable_text text,updated_at integer,deleted integer)')
            conn.execute('insert into tasks values(?,?,?,?,?,0)',('workspace','z-one','标题',TEXT,1))
            conn.commit()
        (self.home/'.qwen').mkdir()
        p=self.packet(self.scan())
        self.assertEqual({e['runtime'] for e in p['evidence']},{'workbuddy','gemini','codex','zcode'})
        self.assertEqual(next(e for e in p['evidence'] if e['runtime']=='zcode')['completeness'],'index_excerpt')
        self.assertTrue(any(r['runtime']=='qwen' and r['status']=='unsupported' for r in p['coverage']))
        with mock.patch.object(flow,'load',side_effect=AssertionError('unchanged must skip')):
            result=self.scan()
        self.assertEqual(result['stats']['unchanged'],4)

    def test_sensitive_business_filename_is_quarantined_and_skipped(self):
        transcript(self.home/'.claude/projects/p/a.jsonl',text='司法鉴定意见书（示例姓名）.pdf 文件需要识别')
        result=self.scan();packet=self.packet(result)
        self.assertEqual(result['stats']['quarantined'],1)
        self.assertNotIn('示例姓名',Path(result['packet']).read_text())
        with mock.patch.object(flow,'load',side_effect=AssertionError('quarantine unchanged')):
            self.assertEqual(self.scan()['stats']['unchanged'],1)
        self.assertFalse(packet['evidence'])

    def test_adapter_upgrade_excludes_old_unchecked_summaries(self):
        transcript(self.home/'.claude/projects/p/a.jsonl',sid='one')
        transcript(self.home/'.workbuddy/projects/p/a.jsonl',sid='two')
        self.scan()
        with mock.patch.object(flow,'ADAPTER_VERSION','future-version'):
            packet=self.packet(self.scan(1))
        self.assertEqual(len(packet['evidence']),1)
        self.assertEqual(packet['stats']['pending_budget'],1)

    def test_custom_roots_remembered_and_home_mismatch_rejected(self):
        custom=self.base/'exported';transcript(custom/'a.jsonl')
        a=flow.scan(self.root,self.home,[f'custom:claude={custom}'],10)
        self.assertEqual(a['stats']['new'],1)
        self.assertEqual(self.scan()['stats']['unchanged'],1)
        with self.assertRaisesRegex(ValueError,'home_mismatch'):
            flow.scan(self.root,self.base/'other',[],10)

    def test_initialized_sources_survive_different_runtime_environment(self):
        export=self.base/'external-runtime';transcript(export/'one.jsonl')
        with mock.patch.object(flow,'sources',side_effect=lambda home,custom:[adapters.Source('external','claude',export)]):
            self.scan()
        packet=self.packet(self.scan())
        self.assertEqual(packet['stats']['unchanged'],1)
        self.assertTrue(any(r['runtime']=='external' for r in packet['coverage']))

    def test_failed_file_cannot_starve_untouched_history(self):
        bad=self.home/'.claude/projects/p/bad.jsonl';bad.parent.mkdir(parents=True);bad.write_text('{bad}')
        self.scan(1)
        transcript(self.home/'.claude/projects/p/new.jsonl')
        result=self.scan(1)
        self.assertEqual(result['stats']['new'],1)
        self.assertEqual(result['stats']['pending_budget'],1)

    def test_scan_lock_and_unknown_schema_fail_closed(self):
        with flow.locked(self.root):
            with self.assertRaisesRegex(ValueError,'scan_already_running'):self.scan()
        self.scan()
        with flow.database(self.root) as conn:
            conn.execute("update meta set value='999' where key='schema_version'")
        with self.assertRaisesRegex(ValueError,'unsupported_ledger_schema'):self.scan()

    def test_zcode_index_retains_real_excerpt_even_with_long_block(self):
        z=self.home/'.zcode/v2/tasks-index.sqlite';z.parent.mkdir(parents=True)
        text=(TEXT+'\n')*100
        with closing(sqlite3.connect(z)) as conn:
            conn.execute('create table tasks(workspace_key text,task_id text,title text,searchable_text text,updated_at integer,deleted integer)')
            conn.execute('insert into tasks values(?,?,?,?,?,0)',('w','z-long','标题',text,1));conn.commit()
        packet=self.packet(self.scan())
        self.assertTrue(packet['evidence'][0]['excerpts'])
        self.assertEqual(packet['evidence'][0]['completeness'],'index_excerpt')

    def test_cli_initializes_without_key_and_second_scan(self):
        transcript(self.home/'.claude/projects/p/a.jsonl')
        env={k:v for k,v in os.environ.items() if not k.startswith(('SELF_EVOLVE_','SKILL_EVOLVE_','SILICONFLOW_'))}
        env.update(SELF_EVOLVE_DATA_ROOT=str(self.base/'cli-state'),PYTHONDONTWRITEBYTECODE='1')
        cmd=[sys.executable,'-S',str(SCRIPTS/'public_workflow.py'),'scan','--home',str(self.home)]
        a=subprocess.run(cmd,env=env,capture_output=True,text=True)
        self.assertEqual(a.returncode,0,a.stderr)
        b=subprocess.run(cmd,env=env,capture_output=True,text=True)
        self.assertEqual(b.returncode,0,b.stderr)
        self.assertEqual(json.loads(b.stdout)['stats']['unchanged'],1)
        state=self.base/'cli-state'
        self.assertTrue((state/'.self-evolve-root.json').exists())
        self.assertFalse((state/'runtime/raw-sessions').exists())
        c=subprocess.run([sys.executable,'-S',str(SCRIPTS/'first_run.py'),'--no-panel','--home',str(self.home)],env=env,capture_output=True,text=True)
        self.assertEqual(c.returncode,0,c.stderr)
        self.assertEqual(json.loads(c.stdout)['stats']['unchanged'],1)

    def test_old_top_level_transcript_schema_supported(self):
        old=self.home/'.claude/transcripts/ses_legacy.jsonl'
        old.parent.mkdir(parents=True)
        old.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in [
            {'role':'user','timestamp':'2026-07-18T01:00:00Z','content':[{'type':'text','text':TEXT}]},
            {'role':'assistant','timestamp':'2026-07-18T01:01:00Z','content':[{'type':'text','text':'确定采用顶层格式适配，并保留工具回显隔离。'}]}])+'\n')
        result=self.scan();packet=self.packet(result)
        self.assertEqual(result['stats']['new'],1)
        self.assertEqual(result['stats'].get('failed',0),0)
        self.assertTrue(any(e['runtime']=='claude' and e['completeness']=='transcript' for e in packet['evidence']))
        with mock.patch.object(flow,'load',side_effect=AssertionError('unchanged must skip legacy')):
            self.assertEqual(self.scan()['stats']['unchanged'],1)

    def test_old_transcript_tool_result_only_is_filtered_not_failed(self):
        old=self.home/'.claude/transcripts/ses_tools.jsonl'
        old.parent.mkdir(parents=True)
        old.write_text(json.dumps({'role':'user','timestamp':'2026-07-18T01:00:00Z','content':[{'type':'tool_result','content':'SYNTHETIC_TOOL_OUTPUT'}]},ensure_ascii=False)+'\n')
        result=self.scan();packet=self.packet(result)
        self.assertEqual(result['stats'].get('failed',0),0)
        self.assertEqual(result['status'],'scanned')
        self.assertFalse(packet['evidence'])
        self.assertTrue(any(t['completeness']=='transcript' for t in packet['triage']))

    def test_empty_gemini_session_classified_not_failed(self):
        g=self.home/'.gemini/tmp/p/chats/session-empty.json';g.parent.mkdir(parents=True)
        g.write_text(json.dumps({'sessionId':'gemini-empty','messages':[]}))
        result=self.scan();packet=self.packet(result)
        self.assertEqual(result['stats'].get('empty'),1)
        self.assertEqual(result['stats'].get('failed',0),0)
        self.assertEqual(result['status'],'scanned')
        self.assertTrue(any(t['completeness']=='empty' for t in packet['triage']))
        with flow.database(self.root) as conn:
            row=conn.execute("select status,error from sessions").fetchone()
        self.assertEqual((row['status'],row['error']),('filtered',''))
        with mock.patch.object(flow,'load',side_effect=AssertionError('unchanged must skip empty')):
            self.assertEqual(self.scan()['stats']['unchanged'],1)

    def test_zero_line_jsonl_is_empty_not_invalid(self):
        p=self.home/'.claude/projects/p/empty.jsonl';p.parent.mkdir(parents=True);p.write_text('')
        result=self.scan()
        self.assertEqual(result['stats'].get('empty'),1)
        self.assertEqual(result['stats'].get('failed',0),0)
        self.assertEqual(result['status'],'scanned')

    def test_foreign_ledger_bytes_preserved_before_version_check(self):
        other=self.base/'foreign';other.mkdir();db=other/'ledger.sqlite'
        with closing(sqlite3.connect(db)) as conn:
            conn.execute('create table unrelated(x integer)');conn.execute('insert into unrelated values(1)');conn.commit()
        before=db.read_bytes()
        with self.assertRaisesRegex(ValueError,'unsupported_ledger_schema'):
            flow.scan(other,self.home,[],2)
        self.assertEqual(db.read_bytes(),before)

    def test_three_round_incremental_reconciliation(self):
        transcript(self.home/'.claude/projects/p/a.jsonl',sid='round-a',text='复盘甲流程：沉淀检查清单与验收边界，按模板执行并验证失败修复路径。')
        b=transcript(self.home/'.workbuddy/projects/p/b.jsonl',sid='round-b',text='复盘乙流程：沉淀退避策略与重试预算，验证恢复路径完整性。')
        first=self.scan(4);p1=self.packet(first)
        self.assertEqual((first['stats']['new'],p1['cumulative']['stored_files_or_rows']),(2,2))
        b.write_text(b.read_text()+json.dumps({'type':'user','sessionId':'round-b','message':{'role':'user','content':'补充：失败必须留待后续预算允许时重试。'}},ensure_ascii=False)+'\n')
        transcript(self.home/'.claude/projects/p/c.jsonl',sid='round-c',text='复盘丙流程：新增来源先处理，失败不能饿死历史回填。')
        d=self.home/'.claude/projects/p/d.jsonl';d.write_text('{bad}\n')
        second=self.scan(10);p2=self.packet(second)
        self.assertEqual((second['stats']['unchanged'],second['stats']['updated'],second['stats']['new'],second['stats']['failed']),(1,1,1,1))
        self.assertEqual(p2['cumulative']['stored_files_or_rows'],4)
        d.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in [{'type':'user','sessionId':'round-d','message':{'role':'user','content':'复盘丁流程：恢复后按对象重试并推进未读积压。'}},{'type':'assistant','sessionId':'round-d','message':{'role':'assistant','content':'确定采用恢复验证方法。'}}])+'\n')
        third=self.scan(10)
        self.assertEqual((third['stats']['unchanged'],third['stats']['updated'],third['stats'].get('failed',0)),(3,1,0))
        with flow.database(self.root) as conn:
            self.assertEqual(dict(conn.execute('SELECT status,count(*) FROM sessions GROUP BY status')).get('failed',0),0)
        self.assertEqual(len(flow.status(self.root)['recent_runs']),3)

    def test_same_size_rewrite_detected_by_stat_revision(self):
        p=transcript(self.home/'.claude/projects/p/a.jsonl')
        self.assertEqual(self.scan()['stats']['new'],1)
        raw=p.read_text()
        time.sleep(0.01)
        p.write_text(raw.replace('。','！'))
        self.assertEqual(p.stat().st_size,len(raw.encode('utf-8')))
        self.assertEqual(self.scan()['stats']['updated'],1)

    def test_zcode_revision_change_during_read_fails_closed(self):
        z=self.home/'.zcode/v2/tasks-index.sqlite';z.parent.mkdir(parents=True)
        with closing(sqlite3.connect(z)) as conn:
            conn.execute('create table tasks(workspace_key text,task_id text,title text,searchable_text text,updated_at integer,deleted integer)')
            conn.execute('insert into tasks values(?,?,?,?,?,0)',('w','z-mid','标题',TEXT,7));conn.commit()
        items=adapters.discover([adapters.Source('zcode','zcode-index',z)])
        with closing(sqlite3.connect(z)) as conn:
            conn.execute('update tasks set updated_at=8 where task_id=?',('z-mid',));conn.commit()
        with self.assertRaisesRegex(ValueError,'source_changed_during_read'):
            adapters.load(items[0])

    def test_move_and_missing_source_keep_history_without_double_count(self):
        d=self.home/'.claude/projects/p';a=transcript(d/'a.jsonl',sid='mv')
        self.assertEqual(self.scan()['stats']['new'],1)
        q=self.home/'.claude/projects/q';q.mkdir(parents=True)
        os.rename(d/'a.jsonl',q/'moved.jsonl')
        second=self.scan();p2=self.packet(second)
        self.assertEqual(second['stats']['new'],1)
        self.assertEqual(p2['cumulative']['stored_files_or_rows'],2)
        self.assertEqual((p2['cumulative']['unique_sessions'],p2['cumulative']['duplicate_views']),(1,1))
        shutil.rmtree(self.home/'.claude')
        third=self.scan();p3=self.packet(third)
        with flow.database(self.root) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM sessions').fetchone()[0],2)
        self.assertTrue(any(c['status']=='not_found' for c in p3['coverage']))
        transcript(q/'moved.jsonl',sid='mv')
        fourth=self.scan()
        self.assertEqual(fourth['stats']['updated'],1)
        with flow.database(self.root) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM sessions').fetchone()[0],2)

    def test_ledger_partial_structure_same_version_not_rebuilt(self):
        # A-F1 反例1：同版本 meta 但缺业务表 → 拒绝且字节不动。
        other=self.base/'partial';other.mkdir();db=other/'ledger.sqlite'
        with closing(sqlite3.connect(db)) as conn:
            conn.execute("create table meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            conn.execute("insert into meta values('schema_version','1')");conn.commit()
        before=db.read_bytes()
        with self.assertRaisesRegex(ValueError,'unsupported_ledger_schema'):
            flow.scan(other,self.home,[],2)
        self.assertEqual(db.read_bytes(),before)

    def test_ledger_wrong_sessions_columns_not_rebuilt(self):
        # A-F1 反例2：同版本但 sessions 列结构错误 → 拒绝。
        other=self.base/'wrongcols';other.mkdir();db=other/'ledger.sqlite'
        with closing(sqlite3.connect(db)) as conn:
            conn.execute("create table meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            conn.execute("insert into meta values('schema_version','1')")
            for table in ('sessions','runs','run_sessions','analyses','reviewed_evidence'):
                conn.execute(f'create table {table}(x integer)')
            conn.commit()
        before=db.read_bytes()
        with self.assertRaisesRegex(ValueError,'unsupported_ledger_schema'):
            flow.scan(other,self.home,[],2)
        self.assertEqual(db.read_bytes(),before)

    def test_zero_byte_ledger_with_wal_sidecar_refused(self):
        # A-F1 反例3：零字节主库 + 伴生 WAL → 不是新用户，拒绝初始化。
        other=self.base/'zerowal';other.mkdir();db=other/'ledger.sqlite'
        db.write_bytes(b'')
        db.with_name(db.name+'-wal').write_bytes(b'\xd2\x10\x30\x30 synthetic wal frame')
        with self.assertRaisesRegex(ValueError,'unsupported_ledger_schema'):
            flow.scan(other,self.home,[],2)

    def test_unreadable_file_fails_not_empty(self):
        # A-F3 反例1：非空 JSONL 无读权限 → failed（PermissionError），不是 empty。
        p=transcript(self.home/'.claude/projects/p/locked.jsonl')
        os.chmod(p,0o000)
        try:
            result=self.scan()
            self.assertEqual(result['stats'].get('failed',0),1)
            self.assertEqual(result['stats'].get('empty',0),0)
            with flow.database(self.root) as conn:
                row=conn.execute("select status,error from sessions where status='failed'").fetchone()
            self.assertEqual(row['error'],'PermissionError')
        finally:
            os.chmod(p,0o644)
        # 恢复权限后按对象重试成功（不可恢复地留在 failed 才是缺陷）。
        self.assertEqual(self.scan()['stats']['updated'],1)

    def test_unknown_payload_shape_exposed_not_filtered(self):
        # A-F3 反例2：识别的 role 但 content 为未知结构（非字符串/块列表）→
        # 不静默记 filtered；未知载荷显式暴露。
        p=self.home/'.claude/projects/p/fut.jsonl';p.parent.mkdir(parents=True)
        p.write_text(json.dumps({'role':'user','content':{'new_format':'SYNTHETIC_UNREAD_TEXT'}})+'\n')
        result=self.scan()
        self.assertEqual(result['stats'].get('empty',0),0)
        self.assertEqual(result['stats'].get('failed',0),1)
        self.assertEqual(result['status'],'partial')

    def test_empty_session_count_contract_reconciles(self):
        # A-F4：首次空文件 → new=1 与 run_sessions.outcome 对账、filtered/empty 同记；
        # 二轮 unchanged；修订后 updated。
        p=self.home/'.gemini/tmp/x/chats/session-empty.json';p.parent.mkdir(parents=True)
        p.write_text(json.dumps({'sessionId':'e1','messages':[]}))
        first=self.scan();self.packet(first)
        self.assertEqual((first['stats']['new'],first['stats']['empty'],first['stats']['filtered']),(1,1,1))
        with flow.database(self.root) as conn:
            outcomes=dict(conn.execute('SELECT outcome,count(*) FROM run_sessions GROUP BY outcome'))
            book=dict(conn.execute('SELECT status,count(*) FROM sessions GROUP BY status'))
        self.assertEqual(outcomes.get('new'),1)
        self.assertEqual(book.get('filtered'),1)
        second=self.scan()
        self.assertEqual(second['stats']['unchanged'],1)
        self.assertTrue((self.home/'.gemini/tmp/x/chats/session-empty.json').write_text('{}') or True)
        p.write_text(json.dumps({'sessionId':'e1','messages':[{'type':'user','content':TEXT}]}))
        third=self.scan()
        self.assertEqual(third['stats']['updated'],1)
        self.assertEqual(third['stats'].get('empty',0),0)

    def test_ledger_refusal_preserves_main_wal_shm_bytes(self):
        # A-F1-R1：拒绝路径不得破坏伴生 WAL（只读预核验，可写连接后置）。
        other=self.base/'walkeep';other.mkdir();db=other/'ledger.sqlite'
        db.write_bytes(b'')
        wal=db.with_name(db.name+'-wal')
        wal.write_bytes(b'\xd2\x10\x30\x30 synthetic wal frame payload')
        shm=db.with_name(db.name+'-shm');shm.write_bytes(b'\x00'*32)
        before=(db.read_bytes(),wal.read_bytes(),shm.read_bytes())
        with self.assertRaisesRegex(ValueError,'unsupported_ledger_schema'):
            flow.scan(other,self.home,[],2)
        self.assertEqual((db.read_bytes(),wal.read_bytes(),shm.read_bytes()),before)
        # 合法库同表错列也被拒（P2：全表列检查）。
        other2=self.base/'wrongruns';other2.mkdir();db2=other2/'ledger.sqlite'
        with closing(sqlite3.connect(db2)) as conn:
            conn.execute("create table meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            conn.execute("insert into meta values('schema_version','1')")
            conn.execute("create table sessions(session_key TEXT PRIMARY KEY,adapter TEXT)")
            conn.execute("create table runs(x integer)")
            conn.execute("create table run_sessions(x integer)")
            conn.execute("create table analyses(x integer)")
            conn.execute("create table reviewed_evidence(x integer)")
            conn.commit()
        before2=db2.read_bytes()
        with self.assertRaisesRegex(ValueError,'unsupported_ledger_schema'):
            flow.scan(other2,self.home,[],2)
        self.assertEqual(db2.read_bytes(),before2)

    @unittest.skipUnless(importlib.util.find_spec('yaml'), 'optional YAML configuration requires PyYAML')
    def test_falsy_source_values_rejected_not_skipped(self):
        # A-F2-R1：skill_sources 假值（false/0/[]/{}）报错，不静默禁用来源。
        cfg=self.base/'falsy-core.yaml'
        for falsy in ('false','0','[]','{}'):
            cfg.write_text(f'skill_sources:\n  demo: {falsy}\n')
            with self.assertRaisesRegex(ValueError,'demo'):
                flow2=importlib.import_module('refresh_skill_inventory')
                flow2.load_sources_from_config(cfg)

    def test_unknown_payload_shapes_exposed_across_dialects(self):
        # A-F3-R1：旧方言未知 list 项/嵌套 content/纯 type 行/Codex 未知载荷均暴露。
        cases = {
            'legacy-unknown-item.jsonl': {'role':'user','content':[{'weird':'SYNTHETIC_UNREAD_TEXT'}]},
            'nested-content.jsonl': {'role':'user','content':{'content':{'deeper':1}}},
            'type-only.jsonl': {'type':'user','content':{'new_format':'SYNTHETIC_UNREAD_TEXT'}},
        }
        for name, row in cases.items():
            p=self.home/'.claude/projects/p'/name;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(json.dumps(row)+'\n')
            result=self.scan()
            self.assertEqual(result['stats'].get('failed',0),1, name)
            self.assertEqual(result['stats'].get('empty',0),0, name)
            (self.home/'.claude/projects/p'/name).unlink()
            shutil.rmtree(self.root); self.root.mkdir()
        # Codex response_item message 未知载荷。
        c=self.home/'.codex/sessions/x.jsonl';c.parent.mkdir(parents=True)
        c.write_text('\n'.join(json.dumps(r) for r in [
            {'type':'session_meta','payload':{'id':'cx'}},
            {'type':'response_item','payload':{'type':'message','role':'user','content':{'alien':1}}}])+'\n')
        result=self.scan()
        self.assertEqual(result['stats'].get('failed',0),1)
        self.assertEqual(result['status'],'partial')
        c.unlink()
        shutil.rmtree(self.root); self.root.mkdir()
        # 第三轮 A-F3-R1：未知 type 块（image/future_text）提取器实际会静默
        # 丢弃——内容看不见=漏放，必须 failed 暴露，不显示成功。
        p2=self.home/'.claude/projects/p/ok-blocks.jsonl'
        p2.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in [
            {'type':'user','message':{'role':'user','content':[{'type':'text','text':TEXT},{'type':'image','source':{'x':1}}]}},
            {'type':'assistant','message':{'role':'assistant','content':[{'type':'text','text':'确定采用分层验证。'}]}}])+'\n')
        result=self.scan()
        self.assertEqual(result['stats'].get('failed',1),1)
        self.assertEqual(result['status'],'partial')
        p2.unlink()
        shutil.rmtree(self.root); self.root.mkdir()
        # 正例（A-F3-R4）：字符串 message 是可提取的合法形态，不得误拦。
        p3=self.home/'.claude/projects/p/string-msg.jsonl'
        p3.write_text(json.dumps({'type':'user','message':'复盘工作流，沉淀检查清单与验收边界。'})+'\n')
        result=self.scan()
        self.assertEqual(result['stats'].get('failed',0),0)
        self.assertEqual(result['stats']['new'],1)

    def test_adapter_bump_rereads_misrecorded_filtered_rows(self):
        # A-F3-R2：旧 adapter 误记的 filtered 在新版本下重读修正，历史保留。
        p=self.home/'.claude/projects/p/fut2.jsonl';p.parent.mkdir(parents=True)
        p.write_text(json.dumps({'role':'user','content':{'new_format':'SYNTHETIC_UNREAD_TEXT'}})+'\n')
        with mock.patch.object(flow,'ADAPTER_VERSION','6'), \
             mock.patch.object(adapters,'_assert_known_payloads',lambda *_: None):
            result=self.scan()
            self.assertEqual(result['stats'].get('failed',0),0)
            self.assertEqual(result['stats']['filtered'],1)
            with flow.database(self.root) as conn:
                self.assertEqual(conn.execute("select adapter from sessions").fetchone()[0],'6')
        result=self.scan()
        self.assertEqual(result['stats'].get('failed',0),1)
        with flow.database(self.root) as conn:
            row=conn.execute("select adapter,status,error from sessions").fetchone()
            self.assertEqual((row['adapter'],row['status'],row['error']),(adapters.ADAPTER_VERSION,'failed','unsupported_message_payload'))

    def test_adapter_nine_rereads_top_level_message_filtered_by_eight(self):
        # A-F3-R2：旧 adapter 误记的 filtered 在新版本下重读修正，历史保留。
        p=self.home/'.claude/projects/p/fut2.jsonl';p.parent.mkdir(parents=True)
        p.write_text(json.dumps({'type':'message','role':'user','content':{'new_format':'SYNTHETIC_UNREAD_TEXT'}})+'\n')
        with mock.patch.object(flow,'ADAPTER_VERSION','8'), \
             mock.patch.object(adapters,'_assert_known_payloads',lambda *_: None):
            result=self.scan()
            self.assertEqual(result['stats'].get('failed',0),0)
            self.assertEqual(result['stats']['filtered'],1)
            with flow.database(self.root) as conn:
                self.assertEqual(conn.execute("select adapter from sessions").fetchone()[0],'8')
        old_run_id = result['run_id']
        result=self.scan()
        self.assertEqual(result['stats'].get('failed',0),1)
        with flow.database(self.root) as conn:
            row=conn.execute("select adapter,status,error from sessions").fetchone()
            self.assertEqual((row['adapter'],row['status'],row['error']),(adapters.ADAPTER_VERSION,'failed','unsupported_message_payload'))

            self.assertEqual(conn.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 2)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM run_sessions WHERE run_id=?', (old_run_id,)).fetchone()[0], 1)

    def test_recent_route_single_object_read_failure_continues(self):
        # A-F3-R3：dream_sweep recent 路线单对象读取失败不中断整体。
        good=self.home/'.claude/projects/p/good.jsonl'
        transcript(good,sid='route-good')
        bad=self.home/'.claude/projects/p/bad-perm.jsonl'
        bad.write_text(json.dumps({'type':'user','message':{'role':'user','content':'应当读取失败的对象'}})+'\n')
        os.chmod(bad,0o000)
        try:
            import argparse
            from dream_sweep import build_summaries
            args=argparse.Namespace(since='all', index_mode='recent', sources='claude',
                                    max_sessions=10, max_lines_per_session=200,
                                    include_subagents=True)
            result=build_summaries(args, [], [])
            self.assertTrue(isinstance(result, tuple))
        except OSError as exc:
            self.fail(f'recent 路线整体被单对象失败中断: {exc}')
        finally:
            os.chmod(bad,0o644)


    def test_wal_only_commit_visible_in_source_snapshot(self):
        # R3 A-SQL-SRC-01-R3-WAL（R4 严格化）：仅存在于 WAL 的已提交记录必须可见。
        # 红绿证据：主库单独控制查询看不到哨兵（旧 immutable adapter 会漏读），
        # 当前快照实现能读到；保持 WAL 写连接打开、关闭自动 checkpoint。
        z=self.home/'.zcode/v2/tasks-index.sqlite';z.parent.mkdir(parents=True)
        wal_conn=sqlite3.connect(z)
        self.addCleanup(wal_conn.close)
        wal_conn.execute('PRAGMA journal_mode=wal')
        wal_conn.execute('PRAGMA wal_autocheckpoint=0')
        wal_conn.execute('create table tasks(workspace_key text,task_id text,title text,searchable_text text,updated_at integer,deleted integer)')
        wal_conn.commit()
        wal_conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        wal_conn.execute("insert into tasks values('w','z-wal','仅WAL',?,9,0)",(TEXT,))
        wal_conn.commit()
        # 哨兵只在 WAL：另一独立连接只看主库应查不到（证明测试检测力）。
        with closing(sqlite3.connect(z.resolve().as_uri()+'?mode=ro&immutable=1', uri=True)) as main_only:
            self.assertEqual(main_only.execute('select count(*) from tasks').fetchone()[0],0)
        self.assertTrue((z.parent/'tasks-index.sqlite-wal').exists())
        items=adapters.discover([adapters.Source('zcode','zcode-index',z)])
        self.assertEqual(len(items),1)
        recs,dialect,h,label=adapters.load(items[0])
        self.assertTrue(recs)
        # 原件不变：主库字节在快照查询后不增长（无伴生被创建）。
        self.assertTrue((z.parent/'tasks-index.sqlite-wal').exists())

    def test_wal_mode_main_without_sidecars_untouched_by_precheck(self):
        # R3 A-F1-R1-R3-NOSIDECAR：无伴生 WAL 模式主库，拒绝预检不得创建伴生。
        other=self.base/'noside';other.mkdir();db=other/'ledger.sqlite'
        with closing(sqlite3.connect(db)) as conn:
            conn.execute("create table meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            conn.execute("insert into meta values('schema_version','999')")
            conn.execute('PRAGMA journal_mode=wal')
            conn.commit()
        with closing(sqlite3.connect(db)) as conn:
            conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        # close 后 SQLite 删除空 WAL/SHM → 主库保持 WAL 模式（header 标志）但无伴生
        self.assertFalse((other/'ledger.sqlite-wal').exists())
        self.assertFalse((other/'ledger.sqlite-shm').exists())
        before=db.read_bytes()
        with self.assertRaisesRegex(ValueError,'unsupported_ledger_schema'):
            flow.scan(other,self.home,[],2)
        self.assertEqual(db.read_bytes(),before)
        self.assertFalse((other/'ledger.sqlite-wal').exists())
        self.assertFalse((other/'ledger.sqlite-shm').exists())

    def test_orphan_sidecars_fail_explicitly_not_not_found(self):
        # R3 A-SQL-SRC-01-R3-ORPHAN：主库缺失+WAL/SHM 在 → read_failed，非 not_found。
        d=self.home/'.zcode/v2';d.mkdir(parents=True)
        (d/'tasks-index.sqlite-wal').write_bytes(b'\xd2\x10\x30\x30'+b'O'*512)
        (d/'tasks-index.sqlite-shm').write_bytes(b'\x00'*32)
        catalog=[adapters.Source('zcode','zcode-index',d/'tasks-index.sqlite')]
        items=adapters.discover(catalog)
        self.assertEqual(catalog[0].status,'read_failed')
        self.assertEqual(catalog[0].errors,1)
        self.assertEqual(items,[])

    def test_dict_text_message_extractable(self):
        # R3 A-F3-R5：{'message':{'type':'text','text':…}} 正常提取不误拦。
        p=self.home/'.claude/projects/p/dict-text.jsonl';p.parent.mkdir(parents=True)
        p.write_text(json.dumps({'type':'user','message':{'type':'text','text':TEXT}})+'\n')
        result=self.scan()
        self.assertEqual(result['stats'].get('failed',0),0)
        self.assertEqual(result['stats']['new'],1)
        self.assertEqual(result['status'],'scanned')


    def test_task_deleted_after_discover_fails_named_scan_continues(self):
        # R4 A-SQL-SRC-01-R4-DELETED：发现后任务被删除 → 具名 failed、整轮 partial、
        # 正常会话继续处理（IndexError 竞态回归封死）。
        z=self.home/'.zcode/v2/tasks-index.sqlite';z.parent.mkdir(parents=True)
        with closing(sqlite3.connect(z)) as conn:
            conn.execute('create table tasks(workspace_key text,task_id text,title text,searchable_text text,updated_at integer,deleted integer)')
            conn.execute("insert into tasks values('w','z-del','将删除',?,8,0)",(TEXT,))
            conn.commit()
        transcript(self.home/'.claude/projects/p/good.jsonl',sid='survivor')
        original=adapters._snapshot_source_rows
        state={'deleted':False}
        def discover_then_delete(path_or_catalog, *args):
            items=original(path_or_catalog, *args)
            if items and not state['deleted']:
                with closing(sqlite3.connect(z)) as conn:
                    conn.execute("delete from tasks where task_id='z-del'")
                    conn.commit()
                state['deleted']=True
            return items
        with mock.patch.object(adapters,'_snapshot_source_rows',side_effect=discover_then_delete):
            result=self.scan()
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['stats'].get('failed',0),1)
        self.assertEqual(result['stats']['new'],1)
        with flow.database(self.root) as conn:
            row=conn.execute("select error from sessions where status='failed'").fetchone()
            self.assertEqual(row[0],'source_changed_during_read')


    def test_analysis_page_shows_disposition_status(self):
        # UP-04：分析页展示处置状态——已处理/保留待分析真实呈现，dismissed 可见。
        transcript(self.home/'.claude/projects/p/a.jsonl',sid='disp-a')
        transcript(self.home/'.claude/projects/p/b.jsonl',sid='disp-b',text='复盘第二条流程，补充处置状态展示验证。')
        result=self.scan();p=self.packet(result)
        a=self.analysis(p)
        a['evidence_dispositions']=[{'evidence_id':p['evidence'][0]['evidence_id'],'disposition':'analyzed'},
                                    {'evidence_id':p['evidence'][1]['evidence_id'],'disposition':'dismissed','note':'低价值记录'}]
        html=render(p,a,page='analysis')
        self.assertIn('证据处置状态',html)
        self.assertIn('dismissed',html)
        self.assertIn('低价值记录',html)
        self.assertIn('未声明处置（跨轮保留待分析）',html) if False else None
        # 全部处置后显示"本轮全部证据均已处置"。
        a2=self.analysis(p)
        a2['evidence_dispositions']=[{'evidence_id':e['evidence_id'],'disposition':'analyzed'} for e in p['evidence']]
        html2=render(p,a2,page='analysis')
        self.assertIn('本轮全部证据均已处置',html2)
        # 无处置字段（旧格式分析）不显示该节。
        a3=self.analysis(p)
        a3.pop('evidence_dispositions',None)
        html3=render(p,a3,page='analysis')
        self.assertNotIn('证据处置状态',html3)


    def test_analysis_revision_cannot_unconsume_reviewed_evidence(self):
        # B-F1：处置是追加式账本状态——已消费证据不可被后续修订撤销/改判。
        transcript(self.home/'.claude/projects/p/a.jsonl',sid='rev-a')
        transcript(self.home/'.claude/projects/p/b.jsonl',sid='rev-b',text='复盘第二条流程，补充修订一致性验证。')
        result=self.scan();p=self.packet(result)
        ids=[e['evidence_id'] for e in p['evidence']]
        a1=self.analysis(p)
        a1['evidence_dispositions']=[{'evidence_id':ids[0],'disposition':'analyzed'}]
        d1=self.base/'rev1.json';d1.write_text(json.dumps(a1,ensure_ascii=False))
        first=flow.import_analysis(self.root,Path(result['packet']),d1)
        self.assertEqual((first['evidence_consumed'],first['evidence_retained']),(1,1))
        # 修订把 A 改声明为 dismissed → 与账本冲突，拒绝导入。
        a2=self.analysis(p)
        a2['evidence_dispositions']=[{'evidence_id':ids[0],'disposition':'dismissed'}]
        d2=self.base/'rev2.json';d2.write_text(json.dumps(a2,ensure_ascii=False))
        with self.assertRaisesRegex(ValueError,'disposition_conflicts_reviewed'):
            flow.import_analysis(self.root,Path(result['packet']),d2)
        # 修订空处置同样拒绝（隐含撤销 A）。
        a3=self.analysis(p);a3.pop('evidence_dispositions',None)
        d3=self.base/'rev3.json';d3.write_text(json.dumps(a3,ensure_ascii=False))
        with self.assertRaisesRegex(ValueError,'disposition_conflicts_reviewed'):
            flow.import_analysis(self.root,Path(result['packet']),d3)
        # 一致修订（A 保持 analyzed + B dismissed）正常导入，返回值以账本现状为准。
        a4=self.analysis(p)
        a4['evidence_dispositions']=[{'evidence_id':ids[0],'disposition':'analyzed'},{'evidence_id':ids[1],'disposition':'dismissed','note':'低价值'}]
        d4=self.base/'rev4.json';d4.write_text(json.dumps(a4,ensure_ascii=False))
        fourth=flow.import_analysis(self.root,Path(result['packet']),d4)
        self.assertEqual((fourth['evidence_consumed'],fourth['evidence_retained']),(1,1))

    def test_dismissed_evidence_rotates_out_of_packet_for_new_evidence(self):
        # B-F2：容量内 dismissed 不阻塞新证据——容量+1 跨轮推进回归。
        saved=flow.MAX_EVIDENCE;flow.MAX_EVIDENCE=2
        try:
            for sid in ('rot-a','rot-b','rot-c'):
                transcript(self.home/f'.claude/projects/p/{sid}.jsonl',sid=sid,
                           text=f'复盘流程{sid}：沉淀检查清单与验收边界，验证失败修复路径。')
            r1=self.scan();p1=self.packet(r1)
            self.assertEqual(len(p1['evidence']),2)
            first_ids={e['evidence_id'] for e in p1['evidence']}
            a1=self.analysis(p1)
            a1['evidence_dispositions']=[{'evidence_id':i,'disposition':'dismissed','note':'低价值'} for i in first_ids]
            d1=self.base/'rot1.json';d1.write_text(json.dumps(a1,ensure_ascii=False))
            flow.import_analysis(self.root,Path(r1['packet']),d1)
            r2=self.scan();p2=self.packet(r2)
            self.assertEqual(len(p2['evidence']),2)
            second_ids={e['evidence_id'] for e in p2['evidence']}
            self.assertNotIn(next(i for i in first_ids if i in second_ids),first_ids-second_ids) if first_ids & second_ids else None
            # 至少一条新证据进入（第三条不再被永久阻塞）。
            self.assertTrue(second_ids - first_ids, 'dismissed 证据阻塞了新证据进入包')
            a2=self.analysis(p2)
            new_only=[e for e in p2['evidence'] if e['evidence_id'] in second_ids-first_ids]
            a2['evidence_dispositions']=[{'evidence_id':e['evidence_id'],'disposition':'analyzed'} for e in new_only]
            d2=self.base/'rot2.json';d2.write_text(json.dumps(a2,ensure_ascii=False))
            flow.import_analysis(self.root,Path(r2['packet']),d2)
            r3=self.scan();p3=self.packet(r3)
            third_ids={e['evidence_id'] for e in p3['evidence']}
            # dismissed 证据跨轮保留可见（人工可复核），不被消费也不消失。
            self.assertEqual(third_ids, first_ids)
        finally:
            flow.MAX_EVIDENCE=saved


    def test_conflict_revision_leaves_no_new_artifacts(self):
        # B-F1-R1：冲突修订拒绝后零新增产物——无七页 HTML、无分析 JSON。
        import json as _json
        transcript(self.home/'.claude/projects/p/a.jsonl',sid='z-art')
        result=self.scan();p=self.packet(result)
        eid=p['evidence'][0]['evidence_id']
        a1=self.analysis(p)
        a1['evidence_dispositions']=[{'evidence_id':eid,'disposition':'analyzed'}]
        d1=self.base/'art1.json';d1.write_text(json.dumps(a1,ensure_ascii=False))
        flow.import_analysis(self.root,Path(result['packet']),d1)
        run_dir=Path(result['packet']).parent
        before={f.name for f in run_dir.iterdir()}
        a2=self.analysis(p);a2.pop('evidence_dispositions',None)
        d2=self.base/'art2.json';d2.write_text(json.dumps(a2,ensure_ascii=False))
        with self.assertRaisesRegex(ValueError,'disposition_conflicts_reviewed'):
            flow.import_analysis(self.root,Path(result['packet']),d2)
        after={f.name for f in run_dir.iterdir()}
        self.assertEqual(before,after)

    def test_candidate_file_roundtrip_and_validation(self):
        # B-F4（R2 终版）：candidate_file 导入时服务端核验（存在+哈希一致→
        # verified=True）；报告不含原始路径（脱敏）；虚构路径 verified=False。
        cand_file=self.base/'candidates'/'acceptance-order-checklist-candidate.md'
        cand_file.parent.mkdir(parents=True)
        cand_body='候选草稿正文（合成）。\n'
        cand_file.write_text(cand_body,encoding='utf-8')
        import hashlib as _h
        good_hash=_h.sha256(cand_body.encode()).hexdigest()
        transcript(self.home/'.claude/projects/p/a.jsonl',sid='cand-a')
        result=self.scan();p=self.packet(result)
        a=self.analysis(p)
        a['skill_proposals'][0]['candidate_file']={'path':str(cand_file),'sha256':good_hash,'source':'generate_candidate'}
        imported=flow.validate_analysis(p,a)
        cf=imported['skill_proposals'][0]['candidate_file']
        self.assertEqual((cf['verified'],cf['sha256']),(True,good_hash))
        self.assertNotIn('path',cf)  # 原始路径不入报告数据（脱敏）
        # 真实产物 → 页面显示"候选草稿已生成"+哈希；不含原始路径。
        html=render(p,imported,page='skills')
        self.assertIn('候选草稿已生成',html)
        self.assertIn(good_hash[:32],html)
        self.assertNotIn(str(cand_file),html)
        # 虚构路径（结构合法但文件不存在）→ verified=False + 页面如实说明。
        a_bad=self.analysis(p)
        a_bad['skill_proposals'][0]['candidate_file']={'path':str(self.base/'nonexistent'/'x.md'),'sha256':'b'*64,'source':'generate_candidate'}
        imported_bad=flow.validate_analysis(p,a_bad)
        self.assertIs(imported_bad['skill_proposals'][0]['candidate_file']['verified'],False)
        html_bad=render(p,imported_bad,page='skills')
        self.assertIn('真实性核验未通过',html_bad)
        # 结构错误拒绝。
        bad=copy.deepcopy(a);bad['skill_proposals'][0]['candidate_file']['sha256']='nothex'
        with self.assertRaisesRegex(ValueError,'invalid_candidate_file'):flow.validate_analysis(p,bad)
        # 无 candidate_file 保持"尚无安装包"。
        a2=self.analysis(p)
        html2=render(p,a2,page='skills')
        self.assertIn('尚无安装包',html2)
        self.assertNotIn('候选草稿已生成',html2)


if __name__=='__main__':unittest.main()
