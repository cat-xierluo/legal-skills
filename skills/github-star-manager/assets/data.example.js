/**
 * 示例数据文件 - data.js
 *
 * 此文件展示了 dashboard.html 所需的数据格式。
 * 运行 `python scripts/main.py --export` 会自动生成此文件。
 *
 * 注意：实际生成的 data.js 包含完整的 GitHub Stars 数据，
 * 此文件仅作为格式参考，请勿提交包含个人数据的文件。
 */

const PROJECTS_DATA = [
  {
    "id": 1136152017,
    "full_name": "owner/repo-name",
    "name": "repo-name",
    "owner": "owner",
    "description": "项目描述",
    "html_url": "https://github.com/owner/repo-name",
    "language": "Python",
    "topics": ["topic1", "topic2"],
    "stargazers_count": 100,
    "forks_count": 20,
    "open_issues_count": 5,
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2026-02-01T00:00:00Z",
    "pushed_at": "2026-02-01T00:00:00Z",
    "avatar_url": "https://avatars.githubusercontent.com/u/123456?v=4",
    "has_new_release": false,
    "value": "high",
    "reason": "",
    "category": "devtools",
    "matched_keywords": ["keyword1", "keyword2"]
  },
  {
    "id": 1234567890,
    "full_name": "example/awesome-project",
    "name": "awesome-project",
    "owner": "example",
    "description": "一个很棒的开源项目",
    "html_url": "https://github.com/example/awesome-project",
    "language": "TypeScript",
    "topics": ["ai", "tools"],
    "stargazers_count": 500,
    "forks_count": 100,
    "open_issues_count": 10,
    "created_at": "2024-06-15T08:30:00Z",
    "updated_at": "2026-02-10T12:00:00Z",
    "pushed_at": "2026-02-09T18:00:00Z",
    "avatar_url": "https://avatars.githubusercontent.com/u/987654?v=4",
    "has_new_release": true,
    "value": "high",
    "reason": "值得关注的新版本",
    "category": "ai",
    "matched_keywords": ["ai", "machine-learning"]
  }
];
