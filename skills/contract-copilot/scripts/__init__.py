#!/usr/bin/env python3
"""Contract Copilot Scripts - 合同审查文档操作工具

提供合同审查的文档操作功能，支持批注和修订两种模式。

使用示例：
    from scripts import ContractReviewer

    reviewer = ContractReviewer("workspace/unpacked")
    node = reviewer.find_text("甲方")
    reviewer.add_comment(node, "建议明确甲方的具体法律主体")
    reviewer.save()
"""

from .docx.reviewer import ContractReviewer
from .report.reporting import render_review_report
from .report.report_docx import write_review_report_docx

__all__ = ["ContractReviewer", "render_review_report", "write_review_report_docx"]
