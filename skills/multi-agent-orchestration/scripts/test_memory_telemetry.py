#!/usr/bin/env python3
"""Telemetry provenance/real-snapshot CLI consumers; never launch a worker."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import mem_budget_probe as probe

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / 'fixtures' / 'memory-admission-261002'
GIB = 1024 ** 3
LEGACY_KEYS = {'schema','status','reason','sources','budget_bytes','budget_source','total_bytes','page_size',
               'availability_basis','available_bytes','reserve_bytes','safe_available_bytes','pressure','swap',
               'slots','effective_available_bytes'}


class MemoryTelemetryTests(unittest.TestCase):
    def healthy(self, **overrides):
        return {'hw_memsize':str(32*GIB)+'\n',
                'vm_stat':'Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 1048576.\n',
                'memory_pressure':'The system has sufficient space.\n',
                'vm_swapusage':'total = 2048.00M used = 100.00M free = 1948.00M\n',
                'kernel_pressure':'1\n', **overrides}

    def evaluate(self, snapshots, budget=3*GIB):
        return probe.evaluate(snapshots,budget,'default')

    def cli(self, path, *args):
        env={k:v for k,v in os.environ.items() if k not in (probe.BUDGET_ENV,probe.FIXTURE_ENV)}
        result=subprocess.run([sys.executable,'-B',str(HERE/'mem_budget_probe.py'),'--json',
                               '--fixture-dir',str(path),*args],env=env,capture_output=True,text=True,timeout=15)
        return result,json.loads(result.stdout)

    def test_frozen_minimum_raw_manifest_has_exact_hashes_and_relative_paths(self):
        manifest=json.loads((FIXTURES/'manifest.json').read_text())
        self.assertEqual(len(manifest['files']),15)
        for item in manifest['files']:
            path=Path(item['path'])
            self.assertFalse(path.is_absolute());self.assertNotIn('..',path.parts)
            raw=(FIXTURES/path).read_bytes()
            self.assertEqual(item['size_bytes'],len(raw))
            self.assertEqual(item['sha256'],hashlib.sha256(raw).hexdigest())
            self.assertNotIn(b'/Users/',raw)

    def test_three_frozen_real_cli_snapshots_parse_but_keep_exact_swap_denial(self):
        available=[31495225344,31597412352,31593299968]
        for index,expected in enumerate(available,1):
            result,value=self.cli(FIXTURES/f'snapshot-{index}')
            self.assertEqual(result.returncode,3,result.stderr)
            self.assertEqual(value['status'],'denied');self.assertEqual(value['slots'],0)
            self.assertEqual(value['available_bytes'],expected)
            self.assertEqual(value['reserve_bytes'],6871947673)
            self.assertEqual(value['safe_available_bytes'],expected-6871947673)
            self.assertEqual(value['availability_basis'],'vm_stat')
            self.assertEqual(value['pressure'],{'level':'critical','tighten_factor':0.0,'signals':['swap_used_ratio=0.95>=0.95']})
            self.assertEqual(set(value),LEGACY_KEYS|{'telemetry'})
            self.assertEqual(set(value['sources']),{'hw_memsize','vm_stat','memory_pressure','vm_swapusage'})
            telemetry=value['telemetry']
            self.assertEqual(telemetry['collection_mode'],'fixture_files')
            self.assertTrue(telemetry['sources']['memory_pressure']['read_success'])
            self.assertTrue(telemetry['sources']['memory_pressure']['parse_valid'])
            self.assertEqual(telemetry['memory_pressure']['reported_free_percent'],84.0)
            self.assertIsNone(telemetry['memory_pressure']['available_percent'])
            self.assertIsNone(telemetry['memory_pressure']['level'])
            self.assertIsNone(telemetry['memory_pressure']['level_source'])
            self.assertEqual(telemetry['kernel_pressure']['value'],1)
            self.assertEqual(telemetry['kernel_pressure']['level'],'normal')
            self.assertEqual(telemetry['kernel_pressure']['value_domain'],'dispatch_notification_bits')
            self.assertFalse(telemetry['kernel_pressure']['used_for_admission'])
            self.assertEqual(telemetry['composite_pressure']['level'],'critical')
            self.assertTrue(telemetry['composite_pressure']['used_for_admission'])

    def test_report_percent_never_becomes_available_bytes_or_level_without_vmstat(self):
        snapshots=self.healthy(vm_stat=None,memory_pressure='System-wide memory free percentage: 84%\n')
        value=self.evaluate(snapshots)
        self.assertEqual(value['status'],'unprobeable')
        self.assertNotIn('available_bytes',value);self.assertNotIn('slots',value)
        self.assertIsNone(value['telemetry']['memory_pressure']['level'])
        self.assertTrue(value['telemetry']['sources']['memory_pressure']['parse_valid'])
        self.assertFalse(value['telemetry']['composite_pressure']['used_for_admission'])
        with tempfile.TemporaryDirectory() as temp:
            for name,raw in snapshots.items():
                if raw is not None:(Path(temp)/probe.FIXTURE_FILES[name]).write_text(raw)
            result,value=self.cli(temp)
            self.assertEqual(result.returncode,1,result.stderr)
            self.assertNotIn('available_bytes',value)

    def test_report_percent_bounds_duplicates_and_unknown_text_are_not_valid_reports(self):
        for text in ('System-wide memory free percentage: -1%\n','System-wide memory free percentage: 101%\n',
                     'System-wide memory free percentage: unknown\n','System-wide memory free percentage: 84%\n'*2,'garbage'):
            self.assertIsNone(probe.parse_memory_pressure(text),text)
        for percent in (0,84,100):
            value=probe.parse_memory_pressure(f'System-wide memory free percentage: {percent}%\n')
            self.assertEqual(value['reported_free_percent'],percent)
            self.assertIsNone(value['available_percent']);self.assertIsNone(value['level'])

    def test_read_success_and_parse_valid_distinct_for_all_five_sources(self):
        for raw,status,read in ((None,'read_failed',False),('','empty',True),('  \n','empty',True),('garbage','unrecognized',True)):
            value=self.evaluate({name:raw for name in probe.FIXTURE_FILES})
            for name,evidence in value['telemetry']['sources'].items():
                self.assertEqual(evidence['read_success'],read,name)
                self.assertFalse(evidence['parse_valid'],name)
                self.assertEqual(evidence['parse_status'],status,name)
            self.assertEqual(value['status'],'unprobeable')
            self.assertIsNone(value['telemetry']['kernel_pressure']['level'])
            # Existing sources remains its legacy coarse truthiness contract.
            self.assertEqual(set(value['sources'].values()),{'ok' if raw else 'failed'})

    def test_native_dispatch_flags_are_observations_not_internal_enum_or_policy(self):
        for flag,level in ((1,'normal'),(2,'warn'),(4,'critical')):
            value=self.evaluate(self.healthy(kernel_pressure=str(flag)+'\n'))
            native=value['telemetry']['kernel_pressure']
            self.assertEqual(native['source'],'kern.memorystatus_vm_pressure_level')
            self.assertEqual(native['value'],flag);self.assertEqual(native['level'],level)
            self.assertFalse(native['used_for_admission'])
            self.assertTrue(value['telemetry']['sources']['kernel_pressure']['parse_valid'])
            self.assertEqual(value['pressure']['level'],'normal');self.assertEqual(value['slots'],4)

    def test_unknown_invalid_multiline_native_flags_cannot_invent_normal(self):
        for raw in ('0\n','3\n','8\n','-1\n','+1\n','1.0\n','01\n','normal\n','1\n2\n','\n1\n','1\n\n','9'*5000):
            value=self.evaluate(self.healthy(kernel_pressure=raw))
            self.assertIsNone(value['telemetry']['kernel_pressure']['level'],raw[:30])
            evidence=value['telemetry']['sources']['kernel_pressure']
            self.assertTrue(evidence['read_success']);self.assertFalse(evidence['parse_valid'])
            self.assertFalse(value['telemetry']['kernel_pressure']['used_for_admission'])
            self.assertEqual(value['pressure']['level'],'normal');self.assertEqual(value['slots'],4)

    def test_native_normal_never_overrides_legacy_critical(self):
        value=self.evaluate(self.healthy(memory_pressure='critical memory situation\n',kernel_pressure='1\n'))
        self.assertEqual(value['pressure']['level'],'critical');self.assertEqual(value['slots'],0)
        self.assertEqual(value['telemetry']['kernel_pressure']['level'],'normal')
        self.assertEqual(value['telemetry']['composite_pressure']['level'],'critical')

    def test_legacy_keyword_and_available_percent_thresholds_keep_original_slots(self):
        cases=[('The system has sufficient space.\n','normal',4),
               ('The system is under increasing pressure.\n','warn',2),
               ('The system is in a critical memory situation.\n','critical',0),
               ('60% available\n','normal',4),('15% available\n','warn',2),('5% available\n','critical',0)]
        for text,level,slots in cases:
            value=self.evaluate(self.healthy(memory_pressure=text))
            self.assertEqual(value['pressure']['level'],level,text);self.assertEqual(value['slots'],slots,text)
            self.assertEqual(set(value['pressure']),{'level','tighten_factor','signals'})

    def test_legacy_percent_fallback_and_report_coexistence_do_not_change_authority(self):
        raw='The system is under increasing pressure. (70% of memory in use, 12% available)\nSystem-wide memory free percentage: 84%\n'
        value=self.evaluate(self.healthy(vm_stat=None,memory_pressure=raw))
        self.assertEqual(value['availability_basis'],'memory_pressure_percent')
        self.assertEqual(value['available_bytes'],int(32*GIB*.12))
        self.assertEqual(value['pressure']['level'],'warn')
        mp=value['telemetry']['memory_pressure']
        self.assertEqual(mp['reported_free_percent'],84);self.assertEqual(mp['available_percent'],12)
        self.assertEqual(mp['level_source'],'keyword')
        self.assertEqual(probe.parse_memory_pressure('60% available\n')['level_source'],'legacy_available_percent')

    def test_disabled_gate_never_claims_composite_or_native_used_for_admission(self):
        for snapshots in ({},self.healthy(kernel_pressure='4\n')):
            value=self.evaluate(snapshots,budget=0)
            self.assertEqual(value['status'],'disabled');self.assertIsNone(value['slots'])
            self.assertFalse(value['telemetry']['kernel_pressure']['used_for_admission'])
            self.assertFalse(value['telemetry']['composite_pressure']['used_for_admission'])

    def test_real_collector_preserves_successful_empty_stdout_and_readonly_native_argv(self):
        success=mock.Mock(returncode=0,stdout='')
        with mock.patch.object(probe.subprocess,'run',return_value=success) as run:
            snapshots=probe.collect_real()
        self.assertTrue(all(value=='' for value in snapshots.values()))
        commands=[call.args[0] for call in run.call_args_list]
        self.assertIn([probe.SYSCTL,'-n','kern.memorystatus_vm_pressure_level'],commands)
        self.assertIn([probe.MEMORY_PRESSURE],commands)
        self.assertEqual(len(commands),5)
        value=self.evaluate(snapshots)
        self.assertTrue(value['telemetry']['sources']['kernel_pressure']['read_success'])
        self.assertFalse(value['telemetry']['sources']['kernel_pressure']['parse_valid'])

    def test_real_collector_errors_never_claim_read_success(self):
        for effect in (OSError('unavailable'),subprocess.TimeoutExpired('fixture',1)):
            with mock.patch.object(probe.subprocess,'run',side_effect=effect):snapshots=probe.collect_real()
            self.assertTrue(all(value is None for value in snapshots.values()))
        with mock.patch.object(probe.subprocess,'run',return_value=mock.Mock(returncode=1,stdout='1\n')):
            snapshots=probe.collect_real()
        self.assertTrue(all(value is None for value in snapshots.values()))


if __name__=='__main__':
    unittest.main()
