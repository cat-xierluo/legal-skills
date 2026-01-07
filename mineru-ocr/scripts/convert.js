// MinerU PDF → Markdown Converter
// 通过 MinerU API 将 PDF/图片等文档转换为 Markdown 格式

// ===== 配置加载 =====
function getSkillRoot(sh) {
  // 使用相对路径：假设从项目根目录调用脚本
  const projectRoot = sh('pwd').trim();
  return projectRoot + "/.claude/skills/mineru-ocr";
}

function loadConfig(skillRoot) {
  const app = Application.currentApplication();
  app.includeStandardAdditions = true;
  const sh = (cmd) => app.doShellScript(cmd);

  // 使用传入的 skillRoot 推导配置目录（Skill 内部）
  const envPath = skillRoot + "/config/.env";

  // 检查配置文件是否存在
  const envExists = sh(`/bin/test -f "${envPath}" && echo 1 || echo 0`).trim();
  if (envExists !== "1") {
    const msg = "\n===============================================\n" +
                "MinerU 配置文件不存在\n" +
                "===============================================\n" +
                "请按以下步骤配置：\n\n" +
                "1. 访问申请 Token：\n" +
                "   https://mineru.net/apiManage/token\n\n" +
                "2. 配置 Token：\n" +
                "   告诉 AI：\"帮我配置 MinerU，Token 是：xxx\"\n\n" +
                "   或手动配置：\n" +
                "   cp " + skillRoot + "/config/.env.example " + skillRoot + "/config/.env\n" +
                "   nano " + skillRoot + "/config/.env\n\n" +
                "Token 有效期：14 天\n";
    throw new Error(msg);
  }

  const envContent = sh(`cat "${envPath}" 2>/dev/null || echo ""`);
  if (!envContent) {
    throw new Error("无法读取配置文件: " + envPath);
  }

  const config = {};
  const lineData = sh(`cat "${envPath}" | tr '\\n' '|' 2>/dev/null || echo ""`);
  const lines = lineData.split('|');

  for (const line of lines) {
    if (!line) continue;
    const trimmed = line.trim();
    if (trimmed && !trimmed.startsWith('#')) {
      const [key, ...valueParts] = trimmed.split('=');
      if (key && valueParts.length > 0) {
        let value = valueParts.join('=').trim();
        if ((value.startsWith('"') && value.endsWith('"')) ||
            (value.startsWith("'") && value.endsWith("'"))) {
          value = value.slice(1, -1);
        }
        config[key] = value;
      }
    }
  }

  // 检查 API Token 是否已配置
  const apiToken = config.MINERU_API_TOKEN || "";
  if (!apiToken || apiToken === "your_token_here" || apiToken.indexOf("example") > -1) {
    const msg = "\n===============================================\n" +
                "MinerU API Token 未配置\n" +
                "===============================================\n" +
                "请按以下步骤配置：\n\n" +
                "1. 访问申请 Token：\n" +
                "   https://mineru.net/apiManage/token\n\n" +
                "2. 配置 Token：\n" +
                "   告诉 AI：\"帮我配置 MinerU，Token 是：xxx\"\n\n" +
                "   或手动编辑：\n" +
                "   nano " + skillRoot + "/config/.env\n" +
                "   设置：MINERU_API_TOKEN=你的Token\n\n" +
                "Token 有效期：14 天\n";
    throw new Error(msg);
  }

  return config;
}

// ===== 核心转换函数 =====
function convert(filePath) {
  const app = Application.currentApplication();
  app.includeStandardAdditions = true;
  const sh = (cmd) => app.doShellScript(cmd);
  const quote = (s) => `'${String(s).replace(/'/g, "'\\''")}'`;

  // 获取 Skill 根目录
  const skillRoot = getSkillRoot(sh);

  // 加载配置
  let config;
  try {
    config = loadConfig(skillRoot);
  } catch (error) {
    throw new Error(`配置加载错误: ${error.message}`);
  }

  // 配置参数
  const API_BASE   = config.MINERU_API_BASE || "https://mineru.net/api/v4";
  const API_TOKEN  = config.MINERU_API_TOKEN || "";
  const USER_TOKEN = config.MINERU_USER_TOKEN || "";
  const ENABLE_OCR     = config.MINERU_ENABLE_OCR === "true";
  const ENABLE_TABLE   = config.MINERU_ENABLE_TABLE === "true";
  const ENABLE_FORMULA = config.MINERU_ENABLE_FORMULA === "true";
  const LANGUAGE_CODE  = config.MINERU_LANGUAGE_CODE || "ch";
  const ALLOWED_EXTS = config.MINERU_ALLOWED_EXTS ?
    config.MINERU_ALLOWED_EXTS.split(',').map(ext => ext.trim()) :
    ["pdf","doc","docx","ppt","pptx","png","jpg","jpeg"];
  const POLL_MAX   = parseInt(config.MINERU_POLL_MAX) || 60;
  const POLL_SLEEP = parseInt(config.MINERU_POLL_SLEEP) || 10;
  const LOG_LEVEL = config.MINERU_LOG_LEVEL || 'low';

  const __LV = { low: 1, medium: 2, high: 3 };
  const __cur = __LV[LOG_LEVEL] || 1;
  const log = (msg, level = 1) => {
    if (__cur >= level) console.log(msg);
  };

  if (!API_TOKEN) {
    throw new Error("缺少 API_TOKEN 配置");
  }

  // 验证文件
  if (!filePath) {
    throw new Error("未提供文件路径");
  }

  const fileName = sh(`/usr/bin/basename ${quote(filePath)}`).trim();
  const fileExists = sh(`/bin/test -f ${quote(filePath)} && echo 1 || echo 0`).trim();
  if (fileExists !== "1") {
    throw new Error(`文件不存在: ${filePath}`);
  }

  const ext = String(filePath).split('.').pop().toLowerCase();
  if (!ALLOWED_EXTS.includes(ext)) {
    throw new Error(`不支持的文件类型: ${ext}`);
  }

  log(`开始转换: ${fileName}`, 2);

  // 创建临时工作目录
  const workDir = sh(`/usr/bin/mktemp -d -t mineru_`).trim();
  const inputFile = `${workDir}/input.${ext}`;

  try {
    // 复制文件到工作目录
    sh(`/bin/cp ${quote(filePath)} ${quote(inputFile)}`);

    // 1. 申请上传地址
    const baseName = fileName;
    const dataId = `convert_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
    const req1 = {
      enable_formula: !!ENABLE_FORMULA,
      language: LANGUAGE_CODE,
      enable_table: !!ENABLE_TABLE,
      files: [{ name: baseName, is_ocr: !!ENABLE_OCR, data_id: dataId }]
    };

    const resp1Path = `${workDir}/resp1.json`;
    const http1 = sh(`/usr/bin/curl -s -X POST ${quote(API_BASE + '/file-urls/batch')} ` +
                    `-H ${quote('Authorization: Bearer ' + API_TOKEN)} ` +
                    (USER_TOKEN ? `-H ${quote('token: ' + USER_TOKEN)} ` : "") +
                    `-H 'Content-Type: application/json' ` +
                    `--data-raw ${quote(JSON.stringify(req1))} ` +
                    `-w '%{http_code}' -o ${quote(resp1Path)}`).trim();

    if (http1 !== "200" && http1 !== "201") {
      const resp1 = sh(`/bin/cat ${quote(resp1Path)}`);

      // 检测 Token 过期或无效
      if (http1 === "401" || http1 === "403" || resp1.indexOf("Unauthorized") > -1 || resp1.indexOf("invalid") > -1) {
        const msg = "\n===============================================\n" +
                    "MinerU API Token 无效或已过期\n" +
                    "===============================================\n" +
                    "HTTP 状态: " + http1 + "\n\n" +
                    "Token 有效期：14 天\n\n" +
                    "解决方法：\n" +
                    "1. 访问重新申请 Token：\n" +
                    "   https://mineru.net/apiManage/token\n\n" +
                    "2. 告诉 AI：\"我的 MinerU Token 过期了，新的 Token 是：xxx\"\n\n" +
                    "   或手动更新：\n" +
                    "   nano " + skillRoot + "/config/.env\n";
        throw new Error(msg);
      }

      throw new Error(`申请上传地址失败 (HTTP ${http1}): ${resp1}`);
    }

    const resp1 = sh(`/bin/cat ${quote(resp1Path)}`);
    const o = JSON.parse(resp1);
    const batchId = o.batch_id || (o.data && o.data.batch_id) || "";
    const fileUrls = o.file_urls || (o.data && o.data.file_urls) || [];
    const ossHeaders = o.headers || (o.data && o.data.headers) || [];
    const uploadURLRaw = Array.isArray(fileUrls) && fileUrls.length > 0 ? fileUrls[0] : "";

    if (!batchId || !uploadURLRaw) {
      throw new Error(`API 响应缺少 batch_id 或 file_urls: ${resp1}`);
    }

    // 使用上传 URL（可能已经是 JSON 字符串或直接 URL）
    let uploadURLClean = uploadURLRaw;
    try {
      uploadURLClean = JSON.parse(uploadURLRaw);
    } catch (e) {
      // 如果不是 JSON，直接使用
    }
    uploadURLClean = uploadURLClean.replace(/[\n\r\t]+/g, " ");

    log(`batchId: ${batchId}`, 3);
    log(`uploadURL: ${uploadURLClean}`, 3);

    // 2. 上传文件到 OSS
    let hdrFlags = "";
    if (Array.isArray(ossHeaders)) {
      const parts = [];
      ossHeaders.forEach((h) => {
        const k = Object.keys(h)[0];
        const v = h[k];
        if (k && typeof v !== 'undefined') {
          parts.push(`-H ${quote(`${k}: ${v}`)}`);
        }
      });
      hdrFlags = parts.join(" ");
    }

    const curlCmd = `/usr/bin/curl -s -X PUT ${hdrFlags} -T ${quote(inputFile)} ${quote(uploadURLClean)} -w '%{http_code}'`;
    log(`上传命令: ${curlCmd}`, 3);

    const httpUp = sh(curlCmd).trim();
    if (httpUp !== "200" && httpUp !== "201") {
      throw new Error(`文件上传失败 (HTTP ${httpUp})`);
    }

    log(`上传成功`, 2);

    // 3. 轮询转换结果
    const pollURL = `${API_BASE}/extract-results/batch/${batchId}`;
    let pollCount = 0;
    let resultUrl = "";
    const pRespPath = `${workDir}/poll_last.json`;

    log(`开始轮询结果...`, 2);

    while (pollCount < POLL_MAX && !resultUrl) {
      sh(`/bin/sleep ${POLL_SLEEP}`);
      pollCount++;

      sh(`/usr/bin/curl -s ${quote(pollURL)} -H ${quote('Authorization: Bearer ' + API_TOKEN)} ` +
         (USER_TOKEN ? `-H ${quote('token: ' + USER_TOKEN)} ` : "") +
         `-o ${quote(pRespPath)}`);

      const pResp = sh(`/bin/cat ${quote(pRespPath)}`);
      const st = JSON.parse(pResp);
      const arr = (st.data && st.data.extract_result) || [];

      if (Array.isArray(arr) && arr.length > 0) {
        const doneItem = arr.find(x => x && x.state === 'done');
        const failItem = arr.find(x => x && x.state === 'failed');
        const first = arr[0] || {};

        if (doneItem && doneItem.full_zip_url) {
          resultUrl = doneItem.full_zip_url;
          log(`处理完成！`, 2);
        } else if (failItem) {
          throw new Error(`MinerU 处理失败: ${failItem.err_msg || '未知错误'}`);
        } else if (pollCount % 10 === 0 || __cur >= 3) {
          const curState = first.state || "unknown";
          log(`处理状态: ${curState} (${pollCount}/${POLL_MAX})`, 2);
        }
      }
    }

    if (!resultUrl) {
      throw new Error(`处理超时，已尝试 ${pollCount} 次`);
    }

    // 4. 下载结果
    const resultFile = `${workDir}/result.zip`;
    sh(`/usr/bin/curl -s -L -o ${quote(resultFile)} "${resultUrl}"`);
    sh(`cd ${quote(workDir)} && /usr/bin/unzip -q result.zip`);

    const mdFile = sh(`/usr/bin/find ${quote(workDir)} -name "*.md" -type f | /usr/bin/head -1`).trim();
    if (!mdFile) {
      throw new Error("未找到 Markdown 文件");
    }

    // 5. 保存 Markdown 到源文件目录
    const originalDir = sh(`/usr/bin/dirname ${quote(filePath)}`).trim();
    const baseNameNoExt = baseName.replace(/\.[^.]+$/, '');
    const outputMdPath = `${originalDir}/${baseNameNoExt}.md`;

    sh(`/bin/cp ${quote(mdFile)} ${quote(outputMdPath)}`);
    log(`已保存: ${outputMdPath}`, 2);

    // 6. 归档完整结果到 Skill 内部
    const archiveDir = `${skillRoot}/archive`;
    const dateStr = new Date().toISOString().split('T')[0].replace(/-/g, '');
    const timestamp = new Date().toISOString().split('T')[1].split('.')[0].replace(/:/g, '');
    const archiveSubDir = `${archiveDir}/${dateStr}_${timestamp}_${baseNameNoExt}`;
    sh(`/bin/mkdir -p ${quote(archiveSubDir)}`);
    sh(`/bin/cp -R ${quote(workDir)}/* ${quote(archiveSubDir)}/`);
    log(`已归档到: ${archiveSubDir}`, 2);

    return {
      success: true,
      outputPath: outputMdPath,
      archivePath: archiveSubDir,
      message: `成功转换 ${fileName} -> ${baseNameNoExt}.md`
    };

  } finally {
    // 清理临时目录
    sh(`/bin/rm -rf ${quote(workDir)}`);
  }
}

// ===== CLI 入口 =====
function run(argv) {
  try {
    if (!argv || argv.length === 0) {
      console.log("用法: osascript -l JavaScript convert.js <文件路径>");
      return "缺少文件路径参数";
    }

    const filePath = argv[0];
    const result = convert(filePath);
    console.log(result.message);
    return result.message;

  } catch (error) {
    const errorMsg = `转换失败: ${error.message}`;
    console.log(errorMsg);
    return errorMsg;
  }
}
