#!/usr/bin/env python3
"""
安全分析器 - 检测 AI Agent/Skill 中的安全风险

基于 OWASP Agentic AI Top 10 和常见漏洞模式设计，
用于识别 skill 中可能存在的恶意代码或安全隐患。
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class SecurityFinding:
    """安全发现"""
    category: str  # 类别
    severity: str  # critical, high, medium, low
    file: str  # 文件路径
    line: int  # 行号
    code: str  # 代码片段
    message: str  # 说明
    pattern: str  # 匹配的模式


# 危险代码模式检测规则
DANGEROUS_PATTERNS = {
    'command_execution': {
        'patterns': [
            r'os\.system\s*\(',
            r'subprocess\.(run|call|Popen|check_output|check_call)\s*\(',
            r'eval\s*\(',
            r'exec\s*\(',
            r'execfile\s*\(',
            r'commands\.getoutput',
            r'child_process\.exec',
            r'child_process\.spawn',
            r'child_process\.execSync',
        ],
        'severity': 'critical',
        'message': '检测到命令执行代码，可能执行任意系统命令',
    },

    'sensitive_file_access': {
        'patterns': [
            r'["\']~/.ssh/',
            r'["\']~/.aws/',
            r'["\']~/.gnupg/',
            r'["\']?\.pem["\']?',
            r'["\']?\.key["\']?',
            r'\.bashrc',
            r'\.zshrc',
            r'\.profile',
            r'\.netrc',
            r'\.pgpass',
            r'_netrc',
            r'id_rsa',
            r'id_ed25519',
            r'authorized_keys',
        ],
        'severity': 'high',
        'message': '检测到敏感文件访问，可能泄露凭证',
    },

    'env_file_access': {
        'patterns': [
            r'open\s*\([^)]*\.env',
            r'load_dotenv',
            r'dotenv\.load',
            r'process\.env\[',  # Node.js
            r'os\.environ',
            r'os\.getenv',
        ],
        'severity': 'medium',
        'message': '检测到环境变量/配置文件访问',
    },

    'data_exfiltration': {
        'patterns': [
            r'requests\.(post|put|patch)\s*\(',
            r'urllib\.request\.urlopen',
            r'urllib\.request\.Request',
            r'httpx\.(post|put|patch)',
            r'axios\.(post|put|patch)',
            r'fetch\s*\(',
            r'XMLHttpRequest',
            r'\.send\s*\(',
        ],
        'severity': 'high',
        'message': '检测到 HTTP 请求，可能向外部发送数据',
    },

    'socket_connection': {
        'patterns': [
            r'socket\.socket',
            r'socket\.connect',
            r'websocket',
            r'WebSocket',
            r'socket\.send',
        ],
        'severity': 'high',
        'message': '检测到 Socket 连接，可能建立隐蔽通信',
    },

    'obfuscation': {
        'patterns': [
            r'base64\.b64decode',
            r'base64\.decode',
            r'codecs\.decode',
            r'__import__\s*\(\s*["\']codecs',
            r'chr\s*\(\s*\d+\s*\)\s*\+',  # chr(111)+chr(112)...
            r'atob\s*\(',
            r'btoa\s*\(',
            r'Buffer\.from\s*\([^)]*,\s*["\']base64["\']',
        ],
        'severity': 'high',
        'message': '检测到代码混淆，可能隐藏恶意行为',
    },

    'privilege_escalation': {
        'patterns': [
            r'\bsudo\b',
            r'\bdoas\b',
            r'chmod\s+777',
            r'chmod\s+\+x',
            r'chmod\s+[0-7]*[0-7]77',
            r'setuid',
            r'setgid',
            r'NOPASSWD',
            r'setcap',
        ],
        'severity': 'critical',
        'message': '检测到权限提升操作',
    },

    'dynamic_import': {
        'patterns': [
            r'__import__\s*\(',
            r'importlib\.import_module',
            r'importlib\.__import__',
            r'globals\s*\(\s*\)\s*\[',
            r'locals\s*\(\s*\)\s*\[',
            r'getattr\s*\([^,]+,\s*[^)]+\)',  # 动态属性访问
            r'require\s*\(\s*[^"\']',  # Node.js 动态 require
        ],
        'severity': 'medium',
        'message': '检测到动态导入，可能加载任意模块',
    },

    'hardcoded_secrets': {
        'patterns': [
            r'(?i)["\']?api_key["\']?\s*[=:]\s*["\'][^"\']{8,}["\']',
            r'(?i)["\']?api-key["\']?\s*[=:]\s*["\'][^"\']{8,}["\']',
            r'(?i)["\']?apikey["\']?\s*[=:]\s*["\'][^"\']{8,}["\']',
            r'(?i)["\']?secret["\']?\s*[=:]\s*["\'][^"\']{8,}["\']',
            r'(?i)["\']?secret_key["\']?\s*[=:]\s*["\'][^"\']{8,}["\']',
            r'(?i)["\']?password["\']?\s*[=:]\s*["\'][^"\']{8,}["\']',
            r'(?i)["\']?passwd["\']?\s*[=:]\s*["\'][^"\']{8,}["\']',
            r'(?i)["\']?token["\']?\s*[=:]\s*["\'][^"\']{8,}["\']',
            r'(?i)["\']?access_token["\']?\s*[=:]\s*["\'][^"\']{8,}["\']',
            r'(?i)["\']?auth_token["\']?\s*[=:]\s*["\'][^"\']{8,}["\']',
            r'(?i)["\']?private_key["\']?\s*[=:]\s*["\'][^"\']{20,}["\']',
            r'AKIA[0-9A-Z]{16}',  # AWS Access Key ID
            r'aws_secret_access_key',
            r'sk-[a-zA-Z0-9]{20,}',  # OpenAI/Anthropic API Key
            r'sk-ant-[a-zA-Z0-9-]+',  # Anthropic API Key
            r'ghp_[a-zA-Z0-9]{36}',  # GitHub Personal Access Token
            r'gho_[a-zA-Z0-9]{36}',  # GitHub OAuth Access Token
            r'ghu_[a-zA-Z0-9]{36}',  # GitHub User-to-Server Token
            r'ghs_[a-zA-Z0-9]{36}',  # GitHub Server-to-Server Token
            r'ghr_[a-zA-Z0-9]{36}',  # GitHub Refresh Token
            r'xox[baprs]-[a-zA-Z0-9-]+',  # Slack Token
            r'glpat-[a-zA-Z0-9-]+',  # GitLab Personal Access Token
            r'(?i)Bearer\s+[a-zA-Z0-9._-]+',  # Bearer Token
        ],
        'severity': 'high',
        'message': '检测到硬编码凭证',
    },

    'download_and_execute': {
        'patterns': [
            r'curl\s+.*\|\s*(bash|sh|zsh|python|node)',
            r'wget\s+.*\|\s*(bash|sh|zsh|python|node)',
            r'curl\s+.*>\s*/tmp/',
            r'wget\s+.*>\s*/tmp/',
            r'Invoke-Expression.*Invoke-WebRequest',  # PowerShell
            r'iex.*DownloadString',  # PowerShell
            r'/dev/tcp/',  # Bash network
        ],
        'severity': 'critical',
        'message': '检测到下载并执行模式，极高风险',
    },

    'file_deletion': {
        'patterns': [
            r'rm\s+-rf\s+/',
            r'rm\s+-rf\s+~',
            r'shutil\.rmtree',
            r'os\.remove',
            r'os\.unlink',
            r'fs\.rmSync',
            r'fs\.unlinkSync',
            r'\.remove\s*\(',
        ],
        'severity': 'high',
        'message': '检测到文件删除操作',
    },

    'process_manipulation': {
        'patterns': [
            r'os\.kill',
            r'signal\.kill',
            r'process\.kill',
            r'pkill',
            r'killall',
            r'taskkill',
        ],
        'severity': 'medium',
        'message': '检测到进程操作',
    },

    'registry_manipulation': {
        'patterns': [
            r'winreg\.',
            r'Register-ScheduledTask',
            r'Set-ItemProperty.*HKLM',
            r'Set-ItemProperty.*HKCU',
            r'reg\s+add',
        ],
        'severity': 'high',
        'message': '检测到注册表操作，可能修改系统设置',
    },

    'persistence': {
        'patterns': [
            r'crontab',
            r'systemctl\s+enable',
            r'launchctl\s+load',
            r'/etc/init\.d/',
            r'/etc/systemd/',
            r'~/Library/LaunchAgents/',
            r'HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run',
            r'ScheduledTask',
        ],
        'severity': 'high',
        'message': '检测到持久化机制',
    },
}

# Skill 特有风险检测
SKILL_RISKS = {
    'hidden_hooks': {
        'patterns': [
            r'post[-_]?install',
            r'pre[-_]?install',
            r'after[-_]?install',
            r'before[-_]?install',
            r'postInstall',
            r'preInstall',
        ],
        'severity': 'high',
        'message': '检测到安装钩子，可能自动执行代码',
    },

    'mcp_server': {
        'patterns': [
            r'@modelcontextprotocol',
            r'mcp[-_]server',
            r'McpServer',
            r'stdio.*transport',
            r'SSE.*transport',
        ],
        'severity': 'medium',
        'message': '检测到 MCP 服务器，可能获取系统访问权限',
    },

    'skill_description_mismatch': {
        'check': 'compare_description_to_code',
        'severity': 'medium',
        'message': 'SKILL.md 描述与代码功能可能不匹配',
    },
}

# 可疑依赖名称（typosquatting 检测）
SUSPICIOUS_PACKAGE_PATTERNS = [
    r'^requests?$',  # 可能是 requests 的拼写错误
    r'^numpy$',  # 检查是否来自官方
    r'^pytol$',  # pylint typo
    r'^djanga$',  # django typo
    r'^flaskk$',  # flask typo
]

# 敏感依赖（可能带来安全风险）
SENSITIVE_DEPENDENCIES = [
    'pickles', 'marshal', 'shelve',  # 序列化风险
    'paramiko', 'fabric', 'asyncssh',  # SSH
    'pexpect', 'ptyprocess',  # 伪终端
    'cryptography', 'pycrypto', 'pycryptodome',  # 加密
]

# 提示词安全检测规则 - 用于检测 SKILL.md 中的恶意提示
PROMPT_SECURITY_PATTERNS = {
    'prompt_injection': {
        'patterns': [
            # 经典提示注入
            r'(?i)ignore\s+(all\s+)?(previous|above|prior)\s+instructions?',
            r'(?i)disregard\s+(all\s+)?(previous|above)\s+instructions?',
            r'(?i)forget\s+(all\s+)?(previous|above)\s+instructions?',
            r'(?i)override\s+(all\s+)?(previous|default)\s+(instructions?|settings?|rules?)',
            r'(?i)bypass\s+(all\s+)?(security|safety|restrictions?|filters?)',
            # 越狱尝试
            r'(?i)jailbreak',
            r'(?i)DAN\s+mode',
            r'(?i)developer\s+mode',
            r'(?i)ignore\s+your\s+training',
            r'(?i)you\s+are\s+now\s+free',
            r'(?i)no\s+restrictions?',
            r'(?i)unrestricted\s+mode',
            # 角色扮演欺骗
            r'(?i)pretend\s+(you\s+are|to\s+be)\s+(a\s+)?(admin|root|system|sudo)',
            r'(?i)act\s+as\s+(if\s+you\s+are\s+)?(admin|root|system|sudo)',
            r'(?i)role[ -]?play\s+as\s+(admin|root|system)',
        ],
        'severity': 'critical',
        'message': '检测到提示注入模式，可能试图绕过安全限制',
    },

    'data_collection_instruction': {
        'patterns': [
            # 收集敏感数据指令
            r'(?i)(collect|gather|harvest|extract)\s+.*\s+(password|token|key|secret|credential)',
            r'(?i)(send|upload|transmit|exfiltrate)\s+.*\s+(to\s+)?(external|third[ -]?party|remote)',
            r'(?i)(read|access|scan)\s+.*\s+\.env\b',
            r'(?i)(read|access|scan)\s+.*\s+(user\s+)?(ssh|aws|gpg)\s+(keys?|credentials?)',
            r'(?i)(copy|steal|exfiltrate)\s+.*\s+(file|data|credential)',
            r'(?i)(export|output)\s+.*\s+(environment|env)\s+variables?',
            r'(?i)(log|record|save)\s+.*\s+(user\s+)?(password|token|api[ -]?key)',
            r'(?i)(capture|intercept)\s+.*\s+(clipboard|input|keystroke)',
        ],
        'severity': 'critical',
        'message': '检测到数据收集指令，可能试图窃取敏感信息',
    },

    'execution_instruction': {
        'patterns': [
            # 在提示词中指令执行命令
            r'(?i)(execute|run|invoke)\s+.*\s+(shell|terminal|command|script)',
            r'(?i)(must|should|always)\s+.*\s+(run|execute)\s+.*\s+(on\s+)?(install|startup|load)',
            r'(?i)(download|fetch)\s+.*\s+and\s+(execute|run|install)',
            r'(?i)curl\s+\S+\s*\|\s*(bash|sh|python|node)',
            r'(?i)wget\s+\S+\s*\|\s*(bash|sh|python|node)',
            r'(?i)(install|setup)\s+.*\s+(automatically|silently|background)',
            r'(?i)(spawn|fork|launch)\s+.*\s+(process|subprocess|child)',
        ],
        'severity': 'high',
        'message': '检测到执行指令，可能在提示词中隐藏恶意执行逻辑',
    },

    'privilege_escalation_instruction': {
        'patterns': [
            # 权限提升指令
            r'(?i)(run|execute)\s+.*\s+with\s+(root|admin|sudo|elevated)\s+(privileges?|access|permissions?)',
            r'(?i)(grant|give|obtain)\s+.*\s+(root|admin|full)\s+(access|permissions?)',
            r'(?i)sudo\s+(apt|yum|brew|pip|npm)',
            r'(?i)(disable|turn\s+off|bypass)\s+.*\s+(security|firewall|antivirus|protection)',
            r'(?i)(modify|edit|change)\s+.*\s+(system|host)\s+(files?|settings?|config)',
        ],
        'severity': 'high',
        'message': '检测到权限提升指令',
    },

    'deceptive_description': {
        'patterns': [
            # 欺骗性描述 - 描述与功能不符
            r'(?i)(simple|harmless|safe|innocent)\s+.*\s+(tool|script|utility)',
            r'(?i)(just|only|merely)\s+.*\s+(checks?|reads?|displays?)\s+.*\s+(file|system|info)',
            r'(?i)for\s+(educational|research|testing)\s+purposes?\s+only',
            r'(?i)(hidden|secret|stealth|covert)\s+.*\s+(feature|mode|function)',
            r'(?i)do\s+not\s+(run|use|execute)\s+.*\s+(in\s+)?(production|real)',
        ],
        'severity': 'medium',
        'message': '检测到可疑的描述模式，可能存在欺骗性说明',
    },

    'network_instruction': {
        'patterns': [
            # 网络外泄指令
            r'(?i)(connect|phone\s+home|beacon)\s+.*\s+(to\s+)?(server|endpoint|api)',
            r'(?i)(post|send|upload)\s+.*\s+(data|file|credential)\s+.*\s+to\s+\S+',
            r'(?i)(establish|create|open)\s+.*\s+(reverse|backdoor|covert)\s+(shell|connection)',
            r'(?i)(ping|check[ -]in)\s+.*\s+(with|to)\s+.*\s+(server|c2|command[ -]and[ -]control)',
            r'(?i)websocket\s+.*\s+(connect|client)',
        ],
        'severity': 'high',
        'message': '检测到网络通信指令，可能存在数据外泄风险',
    },

    'persistence_instruction': {
        'patterns': [
            # 持久化指令
            r'(?i)(add|create|install)\s+.*\s+(cron|scheduled\s+task|startup|launch)',
            r'(?i)(persist|remain|stay)\s+.*\s+(running|active|installed)',
            r'(?i)(auto[ -]?start|auto[ -]?run|auto[ -]?launch)',
            r'(?i)(background|daemon)\s+.*\s+(process|service|task)',
            r'(?i)(modify|edit)\s+.*\s+(\.\w*rc|profile|bashrc|zshrc)',
        ],
        'severity': 'high',
        'message': '检测到持久化指令，可能试图建立长期驻留',
    },

    'hidden_instruction': {
        'patterns': [
            # 隐藏指令 - 使用特殊字符或编码
            r'[\x00-\x08\x0b\x0c\x0e-\x1f]',  # 控制字符
            r'\\u[0-9a-fA-F]{4}',  # Unicode 转义
            r'&#x[0-9a-fA-F]+;',  # HTML 实体
            r'&#[0-9]+;',  # HTML 数字实体
            r'\\x[0-9a-fA-F]{2}',  # 十六进制转义
            # 零宽字符
            r'[\u200b-\u200f\u2028-\u202f\u205f-\u206f]',
        ],
        'severity': 'medium',
        'message': '检测到隐藏字符或编码，可能隐藏恶意内容',
    },

    'social_engineering': {
        'patterns': [
            # 社会工程学模式
            r'(?i)(urgent|critical|important)\s+.*\s+(update|security|patch)',
            r'(?i)(verify|confirm|validate)\s+.*\s+(your\s+)?(identity|account|credential)',
            r'(?i)(winner|won|selected|chosen)\s+.*\s+(for|to)',
            r'(?i)(limited|expires?\s+soon|act\s+now)',
            r'(?i)(trust|safe|verified|official|authentic)',
        ],
        'severity': 'medium',
        'message': '检测到社会工程学模式，可能用于欺骗用户',
    },
}


class SecurityAnalyzer:
    """AI Agent/Skill 安全分析器"""

    def __init__(self, repo_path: str):
        """初始化分析器

        Args:
            repo_path: 仓库本地路径
        """
        self.repo_path = Path(repo_path)
        if not self.repo_path.exists():
            raise ValueError(f"仓库路径不存在: {repo_path}")

        self.findings: List[SecurityFinding] = []
        self.exclude_dirs = {'.git', 'node_modules', '__pycache__', 'venv', '.venv',
                             'dist', 'build', 'target', '.cache', 'vendor'}

    def analyze(self) -> Dict:
        """执行完整安全分析

        Returns:
            安全分析结果
        """
        self.findings = []

        # 执行各项检测
        skill_structure = self._analyze_skill_structure()
        dangerous_patterns = self._detect_dangerous_patterns()
        dependencies = self._analyze_dependencies()
        network = self._analyze_network_activity()
        file_ops = self._analyze_file_operations()
        secrets = self._detect_secrets()
        prompt_security = self._analyze_prompt_security()  # 新增：提示词安全检测

        # 计算风险汇总
        risk_summary = self._calculate_risk_summary()

        return {
            'risk_summary': risk_summary,
            'skill_structure': skill_structure,
            'dangerous_patterns': dangerous_patterns,
            'dependencies': dependencies,
            'network': network,
            'file_operations': file_ops,
            'secrets': secrets,
            'prompt_security': prompt_security,  # 新增
            'findings': self._serialize_findings(),
        }

    def _analyze_skill_structure(self) -> Dict:
        """分析 Skill 结构"""
        result = {
            'is_skill': False,
            'has_skill_md': False,
            'has_scripts': False,
            'has_hooks': False,
            'has_mcp': False,
            'warnings': [],
        }

        # 检查是否是 skill 结构
        skill_md = self.repo_path / 'SKILL.md'
        if skill_md.exists():
            result['has_skill_md'] = True
            result['is_skill'] = True

            # 解析 SKILL.md
            try:
                content = skill_md.read_text(encoding='utf-8')
                result['description'] = self._extract_description(content)

                # 检测 MCP 相关
                if any(p in content.lower() for p in ['mcp', 'modelcontextprotocol']):
                    result['has_mcp'] = True
                    result['warnings'].append('MCP 服务器配置检测到')
            except Exception:
                pass

        # 检查脚本目录
        scripts_dir = self.repo_path / 'scripts'
        if scripts_dir.exists() and scripts_dir.is_dir():
            result['has_scripts'] = True
            script_files = list(scripts_dir.glob('*.py')) + list(scripts_dir.glob('*.js'))
            result['script_count'] = len(script_files)

        # 检查 package.json 中的 hooks
        package_json = self.repo_path / 'package.json'
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text(encoding='utf-8'))
                if 'scripts' in data:
                    hooks = ['postinstall', 'preinstall', 'poststart', 'prestart']
                    for hook in hooks:
                        if hook in data['scripts']:
                            result['has_hooks'] = True
                            result['warnings'].append(f'检测到 npm hook: {hook}')
            except Exception:
                pass

        return result

    def _extract_description(self, content: str) -> str:
        """从 SKILL.md 提取描述"""
        # 尝试从 frontmatter 提取
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                for line in frontmatter.split('\n'):
                    if line.startswith('description:'):
                        return line.split(':', 1)[1].strip().strip('"').strip("'")

        # 尝试从第一段提取
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('---'):
                return line[:200]

        return ""

    def _detect_dangerous_patterns(self) -> Dict:
        """检测危险代码模式"""
        results = defaultdict(list)

        # 获取所有代码文件
        code_extensions = {'.py', '.js', '.jsx', '.ts', '.tsx', '.go', '.rs',
                           '.java', '.sh', '.bash', '.ps1', '.rb', '.php'}
        code_files = []
        for ext in code_extensions:
            code_files.extend(self.repo_path.rglob(f'*{ext}'))

        # 过滤排除目录
        code_files = [f for f in code_files
                      if not any(exc in f.parts for exc in self.exclude_dirs)]

        for file_path in code_files:
            self._scan_file_for_patterns(file_path, results)

        # 合并 Skill 特有检测
        self._scan_skill_risks(results)

        return dict(results)

    def _scan_file_for_patterns(self, file_path: Path, results: Dict):
        """扫描文件中的危险模式"""
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')
            rel_path = str(file_path.relative_to(self.repo_path))

            for category, config in DANGEROUS_PATTERNS.items():
                for pattern in config['patterns']:
                    try:
                        regex = re.compile(pattern, re.IGNORECASE)
                        for i, line in enumerate(lines, 1):
                            if regex.search(line):
                                finding = SecurityFinding(
                                    category=category,
                                    severity=config['severity'],
                                    file=rel_path,
                                    line=i,
                                    code=line.strip()[:100],
                                    message=config['message'],
                                    pattern=pattern,
                                )
                                self.findings.append(finding)
                                results[category].append({
                                    'file': rel_path,
                                    'line': i,
                                    'code': line.strip()[:100],
                                    'severity': config['severity'],
                                    'message': config['message'],
                                })
                    except re.error:
                        pass
        except Exception:
            pass

    def _scan_skill_risks(self, results: Dict):
        """扫描 Skill 特有风险"""
        for category, config in SKILL_RISKS.items():
            if 'patterns' not in config:
                continue

            for file_path in self.repo_path.rglob('*'):
                if not file_path.is_file():
                    continue
                if any(exc in file_path.parts for exc in self.exclude_dirs):
                    continue

                try:
                    content = file_path.read_text(encoding='utf-8', errors='ignore')
                    lines = content.split('\n')
                    rel_path = str(file_path.relative_to(self.repo_path))

                    for pattern in config['patterns']:
                        try:
                            regex = re.compile(pattern, re.IGNORECASE)
                            for i, line in enumerate(lines, 1):
                                if regex.search(line):
                                    finding = SecurityFinding(
                                        category=f'skill_{category}',
                                        severity=config['severity'],
                                        file=rel_path,
                                        line=i,
                                        code=line.strip()[:100],
                                        message=config['message'],
                                        pattern=pattern,
                                    )
                                    self.findings.append(finding)
                                    results[f'skill_{category}'].append({
                                        'file': rel_path,
                                        'line': i,
                                        'code': line.strip()[:100],
                                        'severity': config['severity'],
                                        'message': config['message'],
                                    })
                        except re.error:
                            pass
                except Exception:
                    pass

    def _analyze_dependencies(self) -> Dict:
        """分析依赖安全"""
        result = {
            'package_managers': [],
            'total_dependencies': 0,
            'high_risk_dependencies': [],
            'warnings': [],
        }

        # Python 依赖
        req_files = ['requirements.txt', 'pyproject.toml', 'setup.py', 'Pipfile']
        for req_file in req_files:
            path = self.repo_path / req_file
            if path.exists():
                result['package_managers'].append('python')
                deps = self._parse_python_deps(path)
                result['total_dependencies'] += len(deps)
                result['high_risk_dependencies'].extend(
                    self._check_sensitive_deps(deps, 'python')
                )

        # Node.js 依赖
        package_json = self.repo_path / 'package.json'
        if package_json.exists():
            result['package_managers'].append('nodejs')
            try:
                data = json.loads(package_json.read_text(encoding='utf-8'))
                deps = {**data.get('dependencies', {}), **data.get('devDependencies', {})}
                result['total_dependencies'] += len(deps)
                result['high_risk_dependencies'].extend(
                    self._check_sensitive_deps(list(deps.keys()), 'nodejs')
                )
            except Exception:
                pass

        if result['high_risk_dependencies']:
            result['warnings'].append(
                f"发现 {len(result['high_risk_dependencies'])} 个敏感依赖"
            )

        return result

    def _parse_python_deps(self, path: Path) -> List[str]:
        """解析 Python 依赖文件"""
        deps = []
        try:
            content = path.read_text(encoding='utf-8')
            for line in content.split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    # 提取包名
                    match = re.match(r'^([a-zA-Z0-9_-]+)', line)
                    if match:
                        deps.append(match.group(1))
        except Exception:
            pass
        return deps

    def _check_sensitive_deps(self, deps: List[str], manager: str) -> List[Dict]:
        """检查敏感依赖"""
        high_risk = []
        for dep in deps:
            dep_lower = dep.lower()
            for sensitive in SENSITIVE_DEPENDENCIES:
                if sensitive in dep_lower:
                    high_risk.append({
                        'name': dep,
                        'manager': manager,
                        'risk': f'敏感依赖: {sensitive}',
                    })
        return high_risk

    def _analyze_network_activity(self) -> Dict:
        """分析网络活动"""
        result = {
            'external_urls': [],
            'websockets': [],
            'api_endpoints': [],
            'warnings': [],
        }

        url_pattern = r'https?://[^\s\'"<>]+'
        ws_pattern = r'wss?://[^\s\'"<>]+'

        for file_path in self.repo_path.rglob('*'):
            if not file_path.is_file():
                continue
            if any(exc in file_path.parts for exc in self.exclude_dirs):
                continue
            if file_path.suffix not in {'.py', '.js', '.ts', '.jsx', '.tsx', '.json',
                                         '.md', '.yml', '.yaml', '.sh'}:
                continue

            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                rel_path = str(file_path.relative_to(self.repo_path))

                # 检测 URL
                urls = re.findall(url_pattern, content)
                for url in urls:
                    # 过滤常见的安全 URL
                    if not any(safe in url for safe in
                               ['github.com', 'example.com', 'localhost', '127.0.0.1',
                                'docs.', 'help.', 'readme']):
                        result['external_urls'].append({
                            'file': rel_path,
                            'url': url[:100],
                        })

                # 检测 WebSocket
                ws_urls = re.findall(ws_pattern, content)
                for url in ws_urls:
                    result['websockets'].append({
                        'file': rel_path,
                        'url': url[:100],
                    })

            except Exception:
                pass

        # 去重
        seen_urls = set()
        unique_urls = []
        for item in result['external_urls']:
            if item['url'] not in seen_urls:
                seen_urls.add(item['url'])
                unique_urls.append(item)
        result['external_urls'] = unique_urls[:20]  # 限制数量

        if result['external_urls']:
            result['warnings'].append(f"发现 {len(result['external_urls'])} 个外部 URL")

        return result

    def _analyze_file_operations(self) -> Dict:
        """分析文件操作"""
        result = {
            'sensitive_paths': [],
            'file_operations': [],
            'warnings': [],
        }

        sensitive_paths = [
            '~/.ssh', '~/.aws', '~/.gnupg', '.env', '.pem', '.key',
            '/etc/passwd', '/etc/shadow', '/etc/hosts',
            'id_rsa', 'id_ed25519', 'authorized_keys',
            '.bashrc', '.zshrc', '.profile',
        ]

        for file_path in self.repo_path.rglob('*'):
            if not file_path.is_file():
                continue
            if any(exc in file_path.parts for exc in self.exclude_dirs):
                continue

            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                rel_path = str(file_path.relative_to(self.repo_path))

                for sensitive in sensitive_paths:
                    if sensitive in content:
                        result['sensitive_paths'].append({
                            'file': rel_path,
                            'path': sensitive,
                        })

            except Exception:
                pass

        if result['sensitive_paths']:
            result['warnings'].append(
                f"发现 {len(result['sensitive_paths'])} 处敏感路径引用"
            )

        return result

    def _detect_secrets(self) -> Dict:
        """检测硬编码的敏感信息"""
        result = {
            'findings': [],
            'warnings': [],
        }

        # 使用 hardcoded_secrets 规则
        if 'hardcoded_secrets' not in DANGEROUS_PATTERNS:
            return result

        patterns = DANGEROUS_PATTERNS['hardcoded_secrets']['patterns']

        for file_path in self.repo_path.rglob('*'):
            if not file_path.is_file():
                continue
            if any(exc in file_path.parts for exc in self.exclude_dirs):
                continue
            # 跳过某些文件类型
            if file_path.suffix in {'.png', '.jpg', '.jpeg', '.gif', '.ico',
                                    '.pdf', '.zip', '.tar', '.gz'}:
                continue

            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                lines = content.split('\n')
                rel_path = str(file_path.relative_to(self.repo_path))

                for pattern in patterns:
                    try:
                        regex = re.compile(pattern, re.IGNORECASE)
                        for i, line in enumerate(lines, 1):
                            match = regex.search(line)
                            if match:
                                # 脱敏处理
                                masked_line = self._mask_secret(line, match.group())
                                result['findings'].append({
                                    'file': rel_path,
                                    'line': i,
                                    'type': 'potential_secret',
                                    'masked': masked_line[:100],
                                })
                    except re.error:
                        pass
            except Exception:
                pass

        if result['findings']:
            result['warnings'].append(
                f"发现 {len(result['findings'])} 处可能的硬编码凭证"
            )

        return result

    def _mask_secret(self, line: str, secret: str) -> str:
        """脱敏处理"""
        if len(secret) > 8:
            masked = secret[:4] + '*' * (len(secret) - 8) + secret[-4:]
            return line.replace(secret, masked)
        return line

    def _analyze_prompt_security(self) -> Dict:
        """分析 SKILL.md 和其他 Markdown 文件中的提示词安全

        检测提示注入、数据收集指令、执行指令等恶意模式
        """
        result = {
            'files_analyzed': 0,
            'findings': [],
            'warnings': [],
            'categories_found': set(),
        }

        # 获取所有 Markdown 文件
        md_files = list(self.repo_path.rglob('*.md'))
        # 过滤排除目录
        md_files = [f for f in md_files
                    if not any(exc in f.parts for exc in self.exclude_dirs)]

        for file_path in md_files:
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                rel_path = str(file_path.relative_to(self.repo_path))
                result['files_analyzed'] += 1

                # 对每个文件应用提示词安全检测规则
                self._scan_prompt_content(content, rel_path, result)

            except Exception:
                pass

        # 转换 set 为 list 以便 JSON 序列化
        result['categories_found'] = list(result['categories_found'])

        if result['findings']:
            result['warnings'].append(
                f"在 {result['files_analyzed']} 个 Markdown 文件中发现 "
                f"{len(result['findings'])} 处提示词安全问题"
            )

        return result

    def _scan_prompt_content(self, content: str, file_path: str, result: Dict):
        """扫描 Markdown 内容中的提示词安全风险"""
        lines = content.split('\n')

        for category, config in PROMPT_SECURITY_PATTERNS.items():
            for pattern in config['patterns']:
                try:
                    regex = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                    for i, line in enumerate(lines, 1):
                        match = regex.search(line)
                        if match:
                            # 记录发现
                            finding = {
                                'file': file_path,
                                'line': i,
                                'category': category,
                                'severity': config['severity'],
                                'message': config['message'],
                                'matched_text': match.group()[:50],  # 限制长度
                                'code': line.strip()[:100],
                            }
                            result['findings'].append(finding)
                            result['categories_found'].add(category)

                            # 同时添加到全局 findings 列表
                            security_finding = SecurityFinding(
                                category=f'prompt_{category}',
                                severity=config['severity'],
                                file=file_path,
                                line=i,
                                code=line.strip()[:100],
                                message=f"[提示词安全] {config['message']}",
                                pattern=pattern,
                            )
                            self.findings.append(security_finding)

                except re.error:
                    pass

    def _calculate_risk_summary(self) -> Dict:
        """计算风险汇总"""
        severity_counts = defaultdict(int)
        for finding in self.findings:
            severity_counts[finding.severity] += 1

        # 计算总体风险等级
        if severity_counts['critical'] > 0:
            overall_risk = 'critical'
        elif severity_counts['high'] > 3:
            overall_risk = 'high'
        elif severity_counts['high'] > 0 or severity_counts['medium'] > 5:
            overall_risk = 'medium'
        elif severity_counts['medium'] > 0 or severity_counts['low'] > 0:
            overall_risk = 'low'
        else:
            overall_risk = 'none'

        # 按类别统计
        category_counts = defaultdict(int)
        for finding in self.findings:
            category_counts[finding.category] += 1

        return {
            'overall_risk': overall_risk,
            'total_findings': len(self.findings),
            'severity_counts': dict(severity_counts),
            'category_counts': dict(category_counts),
            'risk_emoji': {
                'critical': '🔴',
                'high': '🟠',
                'medium': '🟡',
                'low': '🟢',
                'none': '✅',
            }.get(overall_risk, '⚪'),
        }

    def _serialize_findings(self) -> List[Dict]:
        """序列化发现结果"""
        return [
            {
                'category': f.category,
                'severity': f.severity,
                'file': f.file,
                'line': f.line,
                'code': f.code,
                'message': f.message,
            }
            for f in self.findings
        ]

    def generate_report(self) -> str:
        """生成安全分析报告"""
        analysis = self.analyze()
        summary = analysis['risk_summary']

        lines = [
            "# 安全分析报告",
            "",
            f"> **分析目标**: {self.repo_path.name}",
            f"> **总体风险等级**: {summary['risk_emoji']} **{summary['overall_risk'].upper()}**",
            "",
            "---",
            "",
            "## 风险概览",
            "",
        ]

        # 严重程度统计
        if summary['total_findings'] > 0:
            lines.append("### 发现统计")
            lines.append("")
            lines.append("| 严重程度 | 数量 |")
            lines.append("|:---------|:-----|")
            for severity in ['critical', 'high', 'medium', 'low']:
                count = summary['severity_counts'].get(severity, 0)
                emoji = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢'}.get(severity, '⚪')
                if count > 0:
                    lines.append(f"| {emoji} {severity.upper()} | {count} |")
            lines.append("")
        else:
            lines.append("✅ **未发现安全风险**")
            lines.append("")

        # Skill 结构分析
        skill_info = analysis['skill_structure']
        if skill_info['is_skill']:
            lines.append("## Skill 结构分析")
            lines.append("")
            lines.append(f"- **SKILL.md**: {'✅ 存在' if skill_info['has_skill_md'] else '❌ 缺失'}")
            lines.append(f"- **脚本目录**: {'✅ 存在' if skill_info['has_scripts'] else '❌ 缺失'}")
            if skill_info.get('has_hooks'):
                lines.append(f"- **安装钩子**: ⚠️ 检测到")
            if skill_info.get('has_mcp'):
                lines.append(f"- **MCP 配置**: ⚠️ 检测到")
            lines.append("")

        # 按类别详细展示
        if analysis['findings']:
            lines.append("## 详细发现")
            lines.append("")

            # 按严重程度分组
            for severity in ['critical', 'high', 'medium', 'low']:
                findings = [f for f in analysis['findings'] if f['severity'] == severity]
                if not findings:
                    continue

                emoji = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢'}.get(severity, '⚪')
                lines.append(f"### {emoji} {severity.upper()} 风险 ({len(findings)})")
                lines.append("")

                # 按类别分组
                by_category = defaultdict(list)
                for f in findings:
                    by_category[f['category']].append(f)

                for category, items in by_category.items():
                    lines.append(f"#### {category}")
                    lines.append("")
                    for item in items[:5]:  # 每个类别最多显示 5 个
                        lines.append(f"- `{item['file']}:{item['line']}`")
                        lines.append(f"  - {item['message']}")
                        lines.append(f"  - 代码: `{item['code']}`")
                    if len(items) > 5:
                        lines.append(f"  - ... 还有 {len(items) - 5} 个")
                    lines.append("")

        # 依赖分析
        deps = analysis['dependencies']
        if deps['high_risk_dependencies']:
            lines.append("## 敏感依赖")
            lines.append("")
            for dep in deps['high_risk_dependencies']:
                lines.append(f"- **{dep['name']}** ({dep['manager']}): {dep['risk']}")
            lines.append("")

        # 外部 URL
        network = analysis['network']
        if network['external_urls']:
            lines.append("## 外部网络请求")
            lines.append("")
            lines.append("| URL | 文件 |")
            lines.append("|:----|:-----|")
            for item in network['external_urls'][:10]:
                lines.append(f"| `{item['url'][:50]}` | `{item['file']}` |")
            if len(network['external_urls']) > 10:
                lines.append(f"| ... | 还有 {len(network['external_urls']) - 10} 个 |")
            lines.append("")

        # 提示词安全分析
        prompt_sec = analysis.get('prompt_security', {})
        if prompt_sec.get('findings'):
            lines.append("## 提示词安全分析")
            lines.append("")
            lines.append(f"> 分析了 {prompt_sec['files_analyzed']} 个 Markdown 文件")
            lines.append("")

            # 按类别分组
            by_category = defaultdict(list)
            for f in prompt_sec['findings']:
                by_category[f['category']].append(f)

            # 类别中文名映射
            category_names = {
                'prompt_injection': '提示注入',
                'data_collection_instruction': '数据收集指令',
                'execution_instruction': '执行指令',
                'privilege_escalation_instruction': '权限提升指令',
                'deceptive_description': '欺骗性描述',
                'network_instruction': '网络通信指令',
                'persistence_instruction': '持久化指令',
                'hidden_instruction': '隐藏指令',
                'social_engineering': '社会工程学',
            }

            for category, items in by_category.items():
                cat_name = category_names.get(category, category)
                severity = items[0]['severity']
                emoji = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢'}.get(severity, '⚪')
                lines.append(f"### {emoji} {cat_name} ({len(items)})")
                lines.append("")
                lines.append(f"*{items[0]['message']}*")
                lines.append("")
                for item in items[:5]:
                    lines.append(f"- `{item['file']}:{item['line']}`")
                    lines.append(f"  - 匹配: `{item['matched_text']}`")
                if len(items) > 5:
                    lines.append(f"- ... 还有 {len(items) - 5} 个")
                lines.append("")

            if prompt_sec.get('warnings'):
                lines.append("**警告:**")
                for warning in prompt_sec['warnings']:
                    lines.append(f"- {warning}")
                lines.append("")

        # 安全建议
        lines.append("## 安全建议")
        lines.append("")

        if summary['overall_risk'] == 'critical':
            lines.append("### 🔴 高危警告")
            lines.append("")
            lines.append("- **强烈建议**：不要在生产环境运行此 skill")
            lines.append("- 需要进行完整的代码审计后才能使用")
            lines.append("- 考虑在沙箱环境中隔离运行")
            lines.append("")
        elif summary['overall_risk'] == 'high':
            lines.append("### 🟠 警告")
            lines.append("")
            lines.append("- 建议在代码审计后使用")
            lines.append("- 注意检查上述发现的安全问题")
            lines.append("- 考虑限制 skill 的访问权限")
            lines.append("")
        elif summary['overall_risk'] == 'medium':
            lines.append("### 🟡 注意")
            lines.append("")
            lines.append("- 使用前请检查上述发现项")
            lines.append("- 建议在测试环境先验证")
            lines.append("")
        else:
            lines.append("### ✅ 低风险")
            lines.append("")
            lines.append("- 未发现明显安全风险")
            lines.append("- 建议定期进行安全检查")
            lines.append("")

        return '\n'.join(lines)


def main():
    """测试入口"""
    import sys

    if len(sys.argv) < 2:
        print("用法: python -m scripts.security <仓库路径>")
        sys.exit(1)

    repo_path = sys.argv[1]
    analyzer = SecurityAnalyzer(repo_path)
    print(analyzer.generate_report())


if __name__ == '__main__':
    main()
