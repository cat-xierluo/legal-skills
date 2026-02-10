# 提交类别参考

本文档定义了 git-batch-commit skill 使用的修改类别及其检测方法。

## 类别

### deps (chore: 依赖管理)
**触发文件：** `package.json`、`requirements.txt`、`go.mod`、`Cargo.toml` 等

**提交格式：** `chore: 更新依赖`

**描述：** 依赖管理文件的变更，包括包管理器的 lockfile。

### docs (docs: 文档)
**触发文件：** `*.md`、`*.rst`、`docs/`、`README*`、`CHANGELOG*`

**提交格式：** `docs: 更新 <主题> 文档`

**描述：** 文档变更。当单个文档文件被修改时，提交信息会包含具体的文档名称。

### license (license: License 文件)
**触发文件：** `LICENSE`、`LICENSE.txt`、`COPYING`

**提交格式：** `license: 更新 license 文件`

**描述：** License 文件的更新。

### config (config: 配置)
**触发文件：** `*.env.*`、`*.conf`、`*.config`、`*.yaml`、`config/`

**提交格式：** `config: 更新配置`

**描述：** 配置文件的变更。

### test (test: 测试)
**触发文件：** `test_*.py`、`*_test.go`、`*.test.ts`、`test/`、`__tests__/`

**提交格式：** `test: 更新测试`

**描述：** 测试文件的添加或修改。

### chore (chore: 工具)
**触发文件：** `Makefile`、`Dockerfile`、`.gitignore`、`.github/`

**提交格式：** `chore: 更新工具`

**描述：** 构建工具、CI/CD 和开发基础设施的变更。

### feat (feat: 新功能)
**触发：** 包含大量添加内容的源代码文件

**提交格式：** `feat: 添加新功能`

**描述：** 添加到代码库的新功能。通过分析 diff 内容中的功能相关关键字和添加/删除比率来检测。

### fix (fix: Bug 修复)
**触发：** diff 中包含 bug 相关关键字的源代码文件

**提交格式：** `fix: 修复 bug`

**描述：** Bug 修复。通过 diff 中的 "fix"、"bug"、"issue"、"error" 等关键字检测。

### refactor (refactor: 代码重构)
**触发：** 删除内容多于添加内容的源代码文件

**提交格式：** `refactor: 重构代码`

**描述：** 无功能性变更的代码重构。

### style (style: 代码风格)
**触发：** 源代码文件（默认类别）

**提交格式：** `style: 更新代码风格`

**描述：** 代码风格变更、格式化或其他小的源代码修改。

## 提交格式规范

所有提交信息遵循格式：**`<类型>: <描述>`**

- 使用小写英文类型前缀（docs:, feat:, fix: 等）
- 使用英文冒号 (:)
- 描述使用中文，保持简洁明确

**GitHub 彩色标签支持：**
使用英文前缀可以让 GitHub 自动识别并显示彩色标签，便于快速浏览提交历史。

## 检测逻辑

1. **文件模式匹配：** 文件首先按路径模式分类
2. **Diff 内容分析：** 对于源代码，分析实际的 diff 以确定是功能、修复、重构还是风格变更
3. **关键字检测：** 查找修复相关关键字（"bug"、"fix"、"error"）与功能关键字（"add"、"new"、"implement"）
4. **行变更比率：** 比较添加与删除以推断意图
