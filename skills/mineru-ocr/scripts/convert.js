// MinerU PDF → Markdown Converter
// 默认 auto 模式：有 Token 走标准 API，无 Token 走免登录轻量接口

ObjC.import("Foundation");
ObjC.import("stdlib");

function readTextFile(path) {
  const data = $.NSData.dataWithContentsOfFile(path);
  if (!data) {
    return "";
  }
  return ObjC.unwrap($.NSString.alloc.initWithDataEncoding(data, $.NSUTF8StringEncoding)) || "";
}

function runShellResult(cmd) {
  const sq = (value) => "'" + String(value).replace(/'/g, "'\\''") + "'";
  const nonce = `${Date.now()}_${Math.floor(Math.random() * 1000000)}`;
  const outPath = `/tmp/mineru_jxa_stdout_${nonce}.txt`;
  const errPath = `/tmp/mineru_jxa_stderr_${nonce}.txt`;
  const statusPath = `/tmp/mineru_jxa_status_${nonce}.txt`;
  const wrapped = `( ${cmd} ) > ${sq(outPath)} 2> ${sq(errPath)}; printf %s $? > ${sq(statusPath)}`;
  const systemStatus = $.system(`/bin/zsh -lc ${sq(wrapped)}`);
  void systemStatus;

  const outputText = readTextFile(outPath);
  const errorText = readTextFile(errPath);
  const statusText = readTextFile(statusPath).trim();
  const exitCode = parseInt(statusText || "1", 10);

  return {
    stdout: String(outputText).replace(/\n$/, ""),
    stderr: String(errorText).replace(/\n$/, ""),
    exitCode: isNaN(exitCode) ? 1 : exitCode
  };
}

function runShell(cmd) {
  const result = runShellResult(cmd);

  if (result.exitCode !== 0) {
    throw new Error((result.stderr || result.stdout || `shell failed (${result.exitCode})`).trim());
  }

  return result.stdout;
}

function shellQuote(value) {
  return "'" + String(value).replace(/'/g, "'\\''") + "'";
}

function getSkillRoot(sh) {
  const projectRoot = sh("pwd").trim();
  return projectRoot + "/.claude/skills/mineru-ocr";
}

function loadConfig(skillRoot) {
  const sh = runShell;
  const envPath = skillRoot + "/config/.env";
  const envExists = sh(`/bin/test -f ${shellQuote(envPath)} && echo 1 || echo 0`).trim() === "1";
  const config = {
    __envPath: envPath,
    __envExists: envExists
  };

  if (!envExists) {
    return config;
  }

  const envContent = sh('/bin/cat ' + shellQuote(envPath) + ' 2>/dev/null || echo ""');
  if (!envContent) {
    throw new Error("无法读取配置文件: " + envPath);
  }

  const lines = envContent.match(/[^\r\n]+/g) || [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }
    const equalIndex = trimmed.indexOf("=");
    if (equalIndex <= 0) {
      continue;
    }
    const key = trimmed.substring(0, equalIndex).trim();
    let value = trimmed.substring(equalIndex + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    config[key] = value;
  }

  return config;
}

function sanitizeConfigValue(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  const lowered = text.toLowerCase();
  if (lowered === "your_token_here" ||
      lowered === "your_mineru_api_token_here" ||
      lowered.indexOf("example") > -1) {
    return "";
  }
  return text;
}

function parseBoolean(value, fallback) {
  if (typeof value === "undefined" || value === null || String(value).trim() === "") {
    return fallback;
  }
  const lowered = String(value).trim().toLowerCase();
  if (["true", "1", "yes", "on"].indexOf(lowered) > -1) {
    return true;
  }
  if (["false", "0", "no", "off"].indexOf(lowered) > -1) {
    return false;
  }
  return fallback;
}

function parseInteger(value, fallback) {
  const parsed = parseInt(value, 10);
  return isNaN(parsed) ? fallback : parsed;
}

function normalizePageRanges(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  return text.replace(/\s+/g, "");
}

function resolveTokenModelVersion(configuredValue, sourceType) {
  if (sourceType === "remote_html_url") {
    return "MinerU-HTML";
  }

  const value = String(configuredValue || "").trim();
  if (value === "vlm") {
    return "vlm";
  }
  return "pipeline";
}

function isHttpUrl(value) {
  return /^https?:\/\//i.test(String(value || "").trim());
}

function hasKnownExtension(name, exts) {
  const lowered = String(name || "").toLowerCase();
  for (let i = 0; i < exts.length; i++) {
    if (lowered.endsWith("." + exts[i])) {
      return true;
    }
  }
  return false;
}

function extractPathWithoutQuery(url) {
  return String(url || "").split("?")[0].split("#")[0];
}

function deriveNameFromUrl(url) {
  const path = extractPathWithoutQuery(url);
  const parts = path.split("/");
  return parts[parts.length - 1] || "remote-document";
}

function sanitizeFileName(name, fallback) {
  const cleaned = String(name || "")
    .replace(/[^0-9A-Za-z._\-\u4e00-\u9fff]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return cleaned || fallback;
}

function isHtmlLikeUrl(url) {
  const path = extractPathWithoutQuery(url).toLowerCase();
  if (path.endsWith(".html") || path.endsWith(".htm")) {
    return true;
  }
  const docExts = ["pdf", "doc", "docx", "ppt", "pptx", "png", "jpg", "jpeg", "jp2", "webp", "gif", "bmp", "xls", "xlsx"];
  return !hasKnownExtension(path, docExts);
}

function zeroPad(num) {
  return num < 10 ? "0" + num : String(num);
}

function buildArchiveSubDir(skillRoot, baseNameNoExt) {
  const now = new Date();
  const dateStr = now.getFullYear() + zeroPad(now.getMonth() + 1) + zeroPad(now.getDate());
  const timeStr = zeroPad(now.getHours()) + zeroPad(now.getMinutes()) + zeroPad(now.getSeconds());
  return `${skillRoot}/archive/${dateStr}_${timeStr}_${baseNameNoExt}`;
}

function writeTextFile(sh, filePath, content) {
  sh(`/usr/bin/printf %s ${shellQuote(content)} > ${shellQuote(filePath)}`);
}

function writeJsonFile(sh, filePath, payload) {
  writeTextFile(sh, filePath, JSON.stringify(payload, null, 2));
}

function readOfficialCliToken(sh) {
  const homeDir = sanitizeConfigValue(sh("/usr/bin/printenv HOME 2>/dev/null || true"));
  if (!homeDir) {
    return "";
  }

  const yamlPath = `${homeDir}/.mineru/config.yaml`;
  const exists = sh(`/bin/test -f ${shellQuote(yamlPath)} && echo 1 || echo 0`).trim() === "1";
  if (!exists) {
    return "";
  }

  const yamlContent = sh(`/bin/cat ${shellQuote(yamlPath)} 2>/dev/null || echo ""`);
  if (!yamlContent) {
    return "";
  }

  const patterns = [
    /^\s*token\s*:\s*["']?([^"'#\r\n]+)["']?\s*$/m,
    /^\s*api_token\s*:\s*["']?([^"'#\r\n]+)["']?\s*$/m,
    /^\s*mineru_token\s*:\s*["']?([^"'#\r\n]+)["']?\s*$/m
  ];

  for (let i = 0; i < patterns.length; i++) {
    const match = yamlContent.match(patterns[i]);
    if (match && match[1]) {
      const token = sanitizeConfigValue(match[1]);
      if (token) {
        return token;
      }
    }
  }

  return "";
}

function resolveApiToken(sh, config) {
  const configuredToken = sanitizeConfigValue(config.MINERU_API_TOKEN);
  if (configuredToken) {
    return configuredToken;
  }
  const envToken = sanitizeConfigValue(sh("/usr/bin/printenv MINERU_API_TOKEN 2>/dev/null || true"));
  if (envToken) {
    return envToken;
  }
  const fallbackEnvToken = sanitizeConfigValue(sh("/usr/bin/printenv MINERU_TOKEN 2>/dev/null || true"));
  if (fallbackEnvToken) {
    return fallbackEnvToken;
  }
  return readOfficialCliToken(sh);
}

function buildTokenSetupHelp(skillRoot, reason) {
  return "\n===============================================\n" +
         "建议配置 MinerU Token\n" +
         "===============================================\n" +
         (reason ? reason + "\n\n" : "") +
         "当前默认使用免登录轻量接口，适合快速转换；如遇到限流、大文件或页数超限，请切换到标准 API。\n\n" +
         "配置方法：\n" +
         "1. 访问申请 Token：\n" +
         "   https://mineru.net/apiManage/token\n\n" +
         "2. 告诉 AI：\"帮我配置 MinerU，Token 是：xxx\"\n\n" +
         "   或手动配置：\n" +
         "   cp " + skillRoot + "/config/.env.example " + skillRoot + "/config/.env\n" +
         "   nano " + skillRoot + "/config/.env\n\n" +
         "当前按最新规则记为：Token 有效期 3 个月（约 90 天）。\n";
}

function buildExpiredTokenHelp(skillRoot, httpStatus) {
  return "\n===============================================\n" +
         "MinerU API Token 无效或已过期\n" +
         "===============================================\n" +
         "HTTP 状态: " + httpStatus + "\n\n" +
         "当前按最新规则记为：Token 有效期 3 个月（约 90 天）。\n\n" +
         "解决方法：\n" +
         "1. 访问重新申请 Token：\n" +
         "   https://mineru.net/apiManage/token\n\n" +
         "2. 告诉 AI：\"我的 MinerU Token 过期了，新的 Token 是：xxx\"\n\n" +
         "   或手动更新：\n" +
         "   nano " + skillRoot + "/config/.env\n";
}

function getAllowedExts(mode) {
  if (mode === "light") {
    return ["pdf", "docx", "pptx", "png", "jpg", "jpeg", "jp2", "webp", "gif", "bmp", "xls", "xlsx"];
  }
  return ["pdf", "doc", "docx", "ppt", "pptx", "png", "jpg", "jpeg"];
}

function tryGetLocalPdfPageCount(sh, filePath) {
  try {
    const mdlsOutput = sh(`/usr/bin/mdls -name kMDItemNumberOfPages -raw ${shellQuote(filePath)} 2>/dev/null || true`).trim();
    const count = parseInteger(mdlsOutput, -1);
    return count > 0 ? count : null;
  } catch (error) {
    return null;
  }
}

function buildOutputInfo(sh, sourceType, sourceValue, baseNameNoExt) {
  if (sourceType === "local_file") {
    return {
      outputDir: sh(`/usr/bin/dirname ${shellQuote(sourceValue)}`).trim(),
      outputBaseName: baseNameNoExt
    };
  }
  return {
    outputDir: sh("pwd").trim(),
    outputBaseName: sanitizeFileName(baseNameNoExt, "remote_document")
  };
}

function buildSourceInfo(sh, source, mode, skillRoot) {
  if (!source) {
    throw new Error("未提供文件路径或 URL");
  }

  if (isHttpUrl(source)) {
    const sourceUrl = String(source).trim();
    const fileName = deriveNameFromUrl(sourceUrl);
    const dotIndex = fileName.lastIndexOf(".");
    const ext = dotIndex > -1 ? fileName.substring(dotIndex + 1).toLowerCase() : "";
    const htmlLike = isHtmlLikeUrl(sourceUrl);
    if (mode === "light" && htmlLike) {
      throw new Error(buildTokenSetupHelp(skillRoot, "网页 URL 提取需要标准 Token API；免登录轻量接口仅支持远程文档 URL，不支持 HTML。"));
    }
    const baseNameNoExt = dotIndex > -1 ? fileName.substring(0, dotIndex) : fileName || "remote-document";
    const output = buildOutputInfo(sh, htmlLike ? "remote_html_url" : "remote_doc_url", sourceUrl, baseNameNoExt);
    return {
      sourceType: htmlLike ? "remote_html_url" : "remote_doc_url",
      sourceValue: sourceUrl,
      fileName: sanitizeFileName(fileName || baseNameNoExt, htmlLike ? "web_page.html" : "remote_document"),
      baseNameNoExt: output.outputBaseName,
      ext: ext,
      outputDir: output.outputDir,
      sizeBytes: null,
      pageCount: null
    };
  }

  const filePath = source;
  const fileExists = sh(`/bin/test -f ${shellQuote(filePath)} && echo 1 || echo 0`).trim();
  if (fileExists !== "1") {
    throw new Error(`文件不存在: ${filePath}`);
  }

  const fileName = sh(`/usr/bin/basename ${shellQuote(filePath)}`).trim();
  const dotIndex = fileName.lastIndexOf(".");
  const ext = dotIndex > -1 ? fileName.substring(dotIndex + 1).toLowerCase() : "";
  const allowedExts = getAllowedExts(mode);

  if (allowedExts.indexOf(ext) === -1) {
    throw new Error(
      `当前${mode === "light" ? "免登录轻量接口" : "标准 Token API"}不支持该文件类型: ${ext || "unknown"}。\n` +
      `支持格式: ${allowedExts.join(", ")}`
    );
  }

  const sizeBytes = parseInteger(sh(`/usr/bin/stat -f%z ${shellQuote(filePath)}`), 0);
  const pageCount = ext === "pdf" ? tryGetLocalPdfPageCount(sh, filePath) : null;
  if (mode === "light" && sizeBytes > 10 * 1024 * 1024) {
    throw new Error(buildTokenSetupHelp(
      skillRoot,
      `当前文件大小约 ${(sizeBytes / 1024 / 1024).toFixed(2)} MB，已超过免登录轻量接口 10 MB 限制。`
    ));
  }
  if (mode === "light" && pageCount && pageCount > 20) {
    throw new Error(buildTokenSetupHelp(
      skillRoot,
      `当前 PDF 共 ${pageCount} 页，已超过免登录轻量接口 20 页限制。`
    ));
  }

  const baseNameNoExt = dotIndex > -1 ? fileName.substring(0, dotIndex) : fileName;
  const output = buildOutputInfo(sh, "local_file", filePath, baseNameNoExt);

  return {
    sourceType: "local_file",
    sourceValue: filePath,
    fileName: fileName,
    baseNameNoExt: output.outputBaseName,
    ext: ext,
    outputDir: output.outputDir,
    sizeBytes: sizeBytes,
    pageCount: pageCount
  };
}

function collectRemoteImageUrls(markdownContent) {
  const urls = [];
  const seen = {};
  const regex = /!\[[^\]]*]\((https?:\/\/[^)\s]+)\)/g;
  let match;
  while ((match = regex.exec(markdownContent)) !== null) {
    const url = match[1];
    if (!seen[url]) {
      seen[url] = true;
      urls.push(url);
    }
  }
  return urls;
}

function safeAssetName(url, index) {
  const cleanUrl = url.split("?")[0].split("#")[0];
  const parts = cleanUrl.split("/");
  let fileName = parts[parts.length - 1] || ("image_" + zeroPad(index + 1) + ".bin");
  fileName = fileName.replace(/[^A-Za-z0-9._-]+/g, "_");
  if (!fileName) {
    fileName = "image_" + zeroPad(index + 1) + ".bin";
  }
  return zeroPad(index + 1) + "_" + fileName;
}

function downloadRemoteImages(sh, archiveSubDir, markdownContent) {
  const urls = collectRemoteImageUrls(markdownContent);
  const manifest = [];
  if (!urls.length) {
    return manifest;
  }

  const imageDir = `${archiveSubDir}/images`;
  sh(`/bin/mkdir -p ${shellQuote(imageDir)}`);

  for (let i = 0; i < urls.length; i++) {
    const url = urls[i];
    const assetName = safeAssetName(url, i);
    const outPath = `${imageDir}/${assetName}`;
    const http = sh(`/usr/bin/curl -s -L ${shellQuote(url)} -w '%{http_code}' -o ${shellQuote(outPath)}`).trim();
    manifest.push({
      url: url,
      archive_path: `images/${assetName}`,
      downloaded: http === "200",
      http_code: http
    });
  }

  return manifest;
}

function finalizeResult(sh, skillRoot, workDir, info, mdFile, extraMeta, log) {
  const outputMdPath = `${info.outputDir}/${info.baseNameNoExt}.md`;
  sh(`/bin/cp ${shellQuote(mdFile)} ${shellQuote(outputMdPath)}`);
  log(`已保存 Markdown: ${outputMdPath}`, 2);

  const archiveSubDir = buildArchiveSubDir(skillRoot, info.baseNameNoExt);
  sh(`/bin/mkdir -p ${shellQuote(archiveSubDir)}`);
  sh(`/bin/cp -R ${shellQuote(workDir)}/. ${shellQuote(archiveSubDir)}/`);

  // 清理已解压的 zip、输入文件副本和 API 返回的原始文件以节省空间
  sh(`/bin/rm -f ${shellQuote(archiveSubDir + "/result.zip")}`);
  sh(`/bin/rm -f ${shellQuote(archiveSubDir + "/input." + info.ext)}`);
  sh(`/usr/bin/find ${shellQuote(archiveSubDir)} -maxdepth 1 -name '*_origin.*' -delete`);

  const archivedMdPath = `${archiveSubDir}/full.md`;
  const mdExists = sh(`/bin/test -f ${shellQuote(archivedMdPath)} && echo 1 || echo 0`).trim() === "1";
  let imageManifest = [];
  if (mdExists) {
    const archivedMdContent = sh(`/bin/cat ${shellQuote(archivedMdPath)}`);
    imageManifest = downloadRemoteImages(sh, archiveSubDir, archivedMdContent);
  }

  // 将 full.md 改名为与输出文件一致的名称
  const archivedMdNewPath = `${archiveSubDir}/${info.baseNameNoExt}.md`;
  sh(`/bin/mv ${shellQuote(archivedMdPath)} ${shellQuote(archivedMdNewPath)}`);

  writeJsonFile(sh, `${archiveSubDir}/conversion_meta.json`, {
    mode: extraMeta.mode,
    source_file: extraMeta.sourceFile,
    output_markdown: outputMdPath,
    archive_path: archiveSubDir,
    detail: extraMeta.detail,
    images: imageManifest
  });

  log(`已归档到: ${archiveSubDir}`, 2);

  return {
    success: true,
    outputPath: outputMdPath,
    archivePath: archiveSubDir,
    mode: extraMeta.mode,
    message: `成功转换 ${info.fileName} -> ${info.baseNameNoExt}.md（${extraMeta.mode === "token" ? "标准 Token API" : "免登录轻量接口"}）` +
      (extraMeta.mode === "light" ? "。提示：轻量模式适合快速使用，若遇到页数/体积/IP 限频，请配置 Token。" : "")
  };
}

function convertLocalFileWithTokenApi(sh, skillRoot, filePath, info, options, log) {
  const API_BASE = sanitizeConfigValue(options.apiBase) || "https://mineru.net/api/v4";
  const API_TOKEN = options.apiToken;
  const workDir = sh("/usr/bin/mktemp -d -t mineru_").trim();
  const inputFile = `${workDir}/input.${info.ext}`;

  try {
    sh(`/bin/cp ${shellQuote(filePath)} ${shellQuote(inputFile)}`);

    const dataId = `convert_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
    const fileItem = {
      name: info.fileName,
      is_ocr: !!options.enableOcr,
      data_id: dataId
    };
    if (options.pageRanges) {
      fileItem.page_ranges = options.pageRanges;
    }
    const req1 = {
      enable_formula: !!options.enableFormula,
      language: options.languageCode,
      enable_table: !!options.enableTable,
      model_version: options.modelVersion,
      files: [fileItem]
    };

    const resp1Path = `${workDir}/upload_ticket.json`;
    const http1 = sh(`/usr/bin/curl -s -X POST ${shellQuote(API_BASE + "/file-urls/batch")} ` +
                     `-H ${shellQuote("Authorization: Bearer " + API_TOKEN)} ` +
                     `-H 'Content-Type: application/json' ` +
                     `--data-raw ${shellQuote(JSON.stringify(req1))} ` +
                     `-w '%{http_code}' -o ${shellQuote(resp1Path)}`).trim();

    if (http1 !== "200" && http1 !== "201") {
      const resp1 = sh(`/bin/cat ${shellQuote(resp1Path)} 2>/dev/null || echo ""`);
      if (http1 === "401" || http1 === "403" || resp1.indexOf("Unauthorized") > -1 || resp1.indexOf("invalid") > -1) {
        throw new Error(buildExpiredTokenHelp(skillRoot, http1));
      }
      throw new Error(`申请上传地址失败 (HTTP ${http1}): ${resp1}`);
    }

    const uploadTicket = JSON.parse(sh(`/bin/cat ${shellQuote(resp1Path)}`));
    const batchId = uploadTicket.batch_id || (uploadTicket.data && uploadTicket.data.batch_id) || "";
    const fileUrls = uploadTicket.file_urls || (uploadTicket.data && uploadTicket.data.file_urls) || [];
    const ossHeaders = uploadTicket.headers || (uploadTicket.data && uploadTicket.data.headers) || [];
    const uploadURLRaw = Array.isArray(fileUrls) && fileUrls.length > 0 ? fileUrls[0] : "";

    if (!batchId || !uploadURLRaw) {
      throw new Error(`API 响应缺少 batch_id 或 file_urls: ${JSON.stringify(uploadTicket)}`);
    }

    let uploadURL = uploadURLRaw;
    try {
      uploadURL = JSON.parse(uploadURLRaw);
    } catch (error) {
      uploadURL = uploadURLRaw;
    }
    uploadURL = String(uploadURL).replace(/[\n\r\t]+/g, " ");

    let headerFlags = "";
    if (Array.isArray(ossHeaders)) {
      const parts = [];
      for (let i = 0; i < ossHeaders.length; i++) {
        const header = ossHeaders[i];
        const key = Object.keys(header)[0];
        const value = header[key];
        if (key && typeof value !== "undefined") {
          parts.push(`-H ${shellQuote(key + ": " + value)}`);
        }
      }
      headerFlags = parts.join(" ");
    }

    const uploadHttp = sh(`/usr/bin/curl -s -X PUT ${headerFlags} -T ${shellQuote(inputFile)} ${shellQuote(uploadURL)} -w '%{http_code}'`).trim();
    if (uploadHttp !== "200" && uploadHttp !== "201") {
      throw new Error(`文件上传失败 (HTTP ${uploadHttp})`);
    }

    log("已上传到标准 Token API，开始轮询结果...", 2);

    const pollURL = `${API_BASE}/extract-results/batch/${batchId}`;
    const pollRespPath = `${workDir}/token_poll.json`;
    let pollCount = 0;
    let resultUrl = "";

    while (pollCount < options.pollMax && !resultUrl) {
      sh(`/bin/sleep ${options.pollSleep}`);
      pollCount += 1;
      sh(`/usr/bin/curl -s ${shellQuote(pollURL)} -H ${shellQuote("Authorization: Bearer " + API_TOKEN)} -o ${shellQuote(pollRespPath)}`);

      const pollResponse = JSON.parse(sh(`/bin/cat ${shellQuote(pollRespPath)}`));
      const resultList = (pollResponse.data && pollResponse.data.extract_result) || [];
      if (Array.isArray(resultList) && resultList.length > 0) {
        let doneItem = null;
        let failedItem = null;
        for (let i = 0; i < resultList.length; i++) {
          const item = resultList[i];
          if (item && item.state === "done" && item.full_zip_url) {
            doneItem = item;
            break;
          }
          if (item && item.state === "failed") {
            failedItem = item;
          }
        }

        if (doneItem) {
          resultUrl = doneItem.full_zip_url;
          break;
        }
        if (failedItem) {
          throw new Error(`MinerU 处理失败: ${failedItem.err_msg || "未知错误"}`);
        }
        if (pollCount % 10 === 0) {
          log(`标准 Token API 处理中 (${pollCount}/${options.pollMax})`, 2);
        }
      }
    }

    if (!resultUrl) {
      throw new Error(`处理超时，已尝试 ${pollCount} 次`);
    }

    const resultFile = `${workDir}/result.zip`;
    sh(`/usr/bin/curl -s -L -o ${shellQuote(resultFile)} ${shellQuote(resultUrl)}`);
    sh(`cd ${shellQuote(workDir)} && /usr/bin/unzip -q result.zip`);

    let discoveredMdFile = sh(`/usr/bin/find ${shellQuote(workDir)} -name "*.md" -type f | /usr/bin/head -1`).trim();
    if (!discoveredMdFile) {
      throw new Error("未找到 Markdown 文件");
    }
    const mdFile = `${workDir}/full.md`;
    if (discoveredMdFile !== mdFile) {
      sh(`/bin/cp ${shellQuote(discoveredMdFile)} ${shellQuote(mdFile)}`);
    }

    return finalizeResult(sh, skillRoot, workDir, info, mdFile, {
      mode: "token",
      sourceFile: filePath,
      detail: {
        api_base: API_BASE,
        batch_id: batchId,
        result_zip_url: resultUrl
      }
    }, log);
  } finally {
    sh(`/bin/rm -rf ${shellQuote(workDir)}`);
  }
}

function convertRemoteUrlWithTokenApi(sh, skillRoot, sourceUrl, info, options, log) {
  const API_BASE = sanitizeConfigValue(options.apiBase) || "https://mineru.net/api/v4";
  const API_TOKEN = options.apiToken;
  const workDir = sh("/usr/bin/mktemp -d -t mineru_url_").trim();

  try {
    const requestBody = {
      url: sourceUrl,
      language: options.languageCode,
      is_ocr: !!options.enableOcr,
      enable_table: !!options.enableTable,
      enable_formula: !!options.enableFormula,
      model_version: options.modelVersion
    };
    if (options.pageRanges && info.sourceType !== "remote_html_url") {
      requestBody.page_ranges = options.pageRanges;
    }

    const createRespPath = `${workDir}/token_url_create.json`;
    const createHttp = sh(`/usr/bin/curl -s -X POST ${shellQuote(API_BASE + "/extract/task")} ` +
                          `-H ${shellQuote("Authorization: Bearer " + API_TOKEN)} ` +
                          `-H 'Content-Type: application/json' ` +
                          `--data-raw ${shellQuote(JSON.stringify(requestBody))} ` +
                          `-w '%{http_code}' -o ${shellQuote(createRespPath)}`).trim();
    const createBody = sh(`/bin/cat ${shellQuote(createRespPath)} 2>/dev/null || echo ""`);
    if (createHttp === "401" || createHttp === "403") {
      throw new Error(buildExpiredTokenHelp(skillRoot, createHttp));
    }
    if (createHttp !== "200" && createHttp !== "201") {
      throw new Error(`创建远程 URL 解析任务失败 (HTTP ${createHttp}): ${createBody}`);
    }

    const createResp = JSON.parse(createBody);
    if (createResp.code !== 0 || !createResp.data || !createResp.data.task_id) {
      throw new Error(`创建远程 URL 解析任务失败: ${createResp.msg || createBody}`);
    }

    log("已提交到标准 Token API（URL 模式），开始轮询结果...", 2);
    const pollRespPath = `${workDir}/token_url_poll.json`;
    let pollCount = 0;
    let resultUrl = "";

    while (pollCount < options.pollMax && !resultUrl) {
      sh(`/bin/sleep ${options.pollSleep}`);
      pollCount += 1;
      const pollHttp = sh(`/usr/bin/curl -s ${shellQuote(API_BASE + "/extract/task/" + createResp.data.task_id)} ` +
                          `-H ${shellQuote("Authorization: Bearer " + API_TOKEN)} ` +
                          `-w '%{http_code}' -o ${shellQuote(pollRespPath)}`).trim();
      const pollBody = sh(`/bin/cat ${shellQuote(pollRespPath)} 2>/dev/null || echo ""`);
      if (pollHttp === "401" || pollHttp === "403") {
        throw new Error(buildExpiredTokenHelp(skillRoot, pollHttp));
      }
      if (pollHttp !== "200" && pollHttp !== "201") {
        throw new Error(`查询远程 URL 任务失败 (HTTP ${pollHttp}): ${pollBody}`);
      }

      const pollResp = JSON.parse(pollBody);
      const data = pollResp.data || {};
      if (data.state === "done" && data.full_zip_url) {
        resultUrl = data.full_zip_url;
        break;
      }
      if (data.state === "failed") {
        throw new Error(`MinerU 处理失败: ${data.err_msg || "未知错误"}`);
      }
      if (pollCount % 10 === 0) {
        log(`标准 Token API（URL 模式）处理中 (${pollCount}/${options.pollMax})`, 2);
      }
    }

    if (!resultUrl) {
      throw new Error(`处理超时，已尝试 ${pollCount} 次`);
    }

    const resultFile = `${workDir}/result.zip`;
    sh(`/usr/bin/curl -s -L -o ${shellQuote(resultFile)} ${shellQuote(resultUrl)}`);
    sh(`cd ${shellQuote(workDir)} && /usr/bin/unzip -q result.zip`);

    const discoveredMdFile = sh(`/usr/bin/find ${shellQuote(workDir)} -name "*.md" -type f | /usr/bin/head -1`).trim();
    if (!discoveredMdFile) {
      throw new Error("未找到 Markdown 文件");
    }
    const mdFile = `${workDir}/full.md`;
    sh(`/bin/cp ${shellQuote(discoveredMdFile)} ${shellQuote(mdFile)}`);

    return finalizeResult(sh, skillRoot, workDir, info, mdFile, {
      mode: "token",
      sourceFile: sourceUrl,
      detail: {
        api_base: API_BASE,
        task_id: createResp.data.task_id,
        result_zip_url: resultUrl,
        source_type: info.sourceType
      }
    }, log);
  } finally {
    sh(`/bin/rm -rf ${shellQuote(workDir)}`);
  }
}

function normalizeLightFailure(skillRoot, httpStatus, rawBody, detail) {
  const body = String(rawBody || "");
  const reason = String(detail || body || "").toLowerCase();
  if (httpStatus === "429" || reason.indexOf("429") > -1 || reason.indexOf("rate") > -1 || reason.indexOf("频率") > -1) {
    return buildTokenSetupHelp(skillRoot, "免登录轻量接口当前触发 IP 限频，请稍后重试或改用标准 Token API。");
  }
  if (reason.indexOf("10mb") > -1 || reason.indexOf("20 page") > -1 || reason.indexOf("20页") > -1 ||
      reason.indexOf("file too large") > -1 || reason.indexOf("page") > -1 || reason.indexOf("size") > -1) {
    return buildTokenSetupHelp(skillRoot, "免登录轻量接口命中了单文件大小或页数限制，请配置 Token 后重试。");
  }
  return null;
}

function convertLocalFileWithLightApi(sh, skillRoot, filePath, info, options, log) {
  const LIGHT_API_BASE = "https://mineru.net/api/v1/agent";
  const workDir = sh("/usr/bin/mktemp -d -t mineru_light_").trim();
  const inputFile = `${workDir}/input.${info.ext}`;

  try {
    sh(`/bin/cp ${shellQuote(filePath)} ${shellQuote(inputFile)}`);

    const submitReq = {
      file_name: info.fileName,
      language: options.languageCode,
      is_ocr: !!options.enableOcr
    };

    const submitRespPath = `${workDir}/light_submit.json`;
    const submitHttp = sh(`/usr/bin/curl -s -X POST ${shellQuote(LIGHT_API_BASE + "/parse/file")} ` +
                          `-H 'Content-Type: application/json' ` +
                          `--data-raw ${shellQuote(JSON.stringify(submitReq))} ` +
                          `-w '%{http_code}' -o ${shellQuote(submitRespPath)}`).trim();
    const submitBody = sh(`/bin/cat ${shellQuote(submitRespPath)} 2>/dev/null || echo ""`);
    const submitHint = normalizeLightFailure(skillRoot, submitHttp, submitBody, "");
    if (submitHint) {
      throw new Error(submitHint);
    }
    if (submitHttp !== "200" && submitHttp !== "201") {
      throw new Error(`免登录轻量接口提交失败 (HTTP ${submitHttp}): ${submitBody}`);
    }

    const submitResp = JSON.parse(submitBody);
    if (submitResp.code !== 0 || !submitResp.data) {
      const detail = submitResp.msg || submitResp.message || submitBody;
      const normalized = normalizeLightFailure(skillRoot, submitHttp, submitBody, detail);
      if (normalized) {
        throw new Error(normalized);
      }
      throw new Error(`免登录轻量接口提交失败: ${detail}`);
    }

    const taskId = submitResp.data.task_id || "";
    const uploadUrl = submitResp.data.file_url || "";
    if (!taskId || !uploadUrl) {
      throw new Error(`免登录轻量接口响应缺少 task_id 或 file_url: ${submitBody}`);
    }

    const uploadHttp = sh(`/usr/bin/curl -s -X PUT -T ${shellQuote(inputFile)} ${shellQuote(uploadUrl)} -w '%{http_code}'`).trim();
    if (uploadHttp !== "200" && uploadHttp !== "201") {
      throw new Error(`免登录轻量接口文件上传失败 (HTTP ${uploadHttp})`);
    }

    log("已提交到免登录轻量接口，开始轮询结果...", 2);

    const pollRespPath = `${workDir}/light_poll.json`;
    let pollCount = 0;
    let markdownUrl = "";
    let finalPollResponse = null;

    while (pollCount < options.pollMax && !markdownUrl) {
      sh(`/bin/sleep ${options.pollSleep}`);
      pollCount += 1;

      const pollHttp = sh(`/usr/bin/curl -s ${shellQuote(LIGHT_API_BASE + "/parse/" + taskId)} -w '%{http_code}' -o ${shellQuote(pollRespPath)}`).trim();
      const pollBody = sh(`/bin/cat ${shellQuote(pollRespPath)} 2>/dev/null || echo ""`);
      const pollHint = normalizeLightFailure(skillRoot, pollHttp, pollBody, "");
      if (pollHint) {
        throw new Error(pollHint);
      }
      if (pollHttp !== "200" && pollHttp !== "201") {
        throw new Error(`免登录轻量接口轮询失败 (HTTP ${pollHttp}): ${pollBody}`);
      }

      const pollResp = JSON.parse(pollBody);
      finalPollResponse = pollResp;
      if (pollResp.code !== 0 || !pollResp.data) {
        const detail = pollResp.msg || pollResp.message || pollBody;
        const normalized = normalizeLightFailure(skillRoot, pollHttp, pollBody, detail);
        if (normalized) {
          throw new Error(normalized);
        }
        throw new Error(`免登录轻量接口轮询失败: ${detail}`);
      }

      const state = pollResp.data.state || "";
      if (state === "done" && pollResp.data.markdown_url) {
        markdownUrl = pollResp.data.markdown_url;
        break;
      }
      if (state === "failed") {
        const detail = pollResp.data.err_msg || pollResp.data.msg || pollBody;
        const normalized = normalizeLightFailure(skillRoot, pollHttp, pollBody, detail);
        if (normalized) {
          throw new Error(normalized);
        }
        throw new Error(`免登录轻量接口处理失败: ${detail}`);
      }
      if (pollCount % 10 === 0) {
        log(`免登录轻量接口处理中 (${pollCount}/${options.pollMax})`, 2);
      }
    }

    if (!markdownUrl) {
      throw new Error(`免登录轻量接口处理超时，已尝试 ${pollCount} 次`);
    }

    const mdFile = `${workDir}/full.md`;
    const mdHttp = sh(`/usr/bin/curl -s -L ${shellQuote(markdownUrl)} -w '%{http_code}' -o ${shellQuote(mdFile)}`).trim();
    if (mdHttp !== "200" && mdHttp !== "201") {
      throw new Error(`下载免登录轻量接口 Markdown 失败 (HTTP ${mdHttp})`);
    }

    if (finalPollResponse) {
      writeJsonFile(sh, `${workDir}/light_result.json`, finalPollResponse);
    }

    return finalizeResult(sh, skillRoot, workDir, info, mdFile, {
      mode: "light",
      sourceFile: filePath,
      detail: {
        task_id: taskId,
        markdown_url: markdownUrl
      }
    }, log);
  } finally {
    sh(`/bin/rm -rf ${shellQuote(workDir)}`);
  }
}

function convertRemoteUrlWithLightApi(sh, skillRoot, sourceUrl, info, options, log) {
  const LIGHT_API_BASE = "https://mineru.net/api/v1/agent";
  const workDir = sh("/usr/bin/mktemp -d -t mineru_light_url_").trim();

  try {
    const submitReq = {
      url: sourceUrl,
      file_name: info.fileName,
      language: options.languageCode,
      is_ocr: !!options.enableOcr
    };

    const submitRespPath = `${workDir}/light_url_submit.json`;
    const submitHttp = sh(`/usr/bin/curl -s -X POST ${shellQuote(LIGHT_API_BASE + "/parse/url")} ` +
                          `-H 'Content-Type: application/json' ` +
                          `--data-raw ${shellQuote(JSON.stringify(submitReq))} ` +
                          `-w '%{http_code}' -o ${shellQuote(submitRespPath)}`).trim();
    const submitBody = sh(`/bin/cat ${shellQuote(submitRespPath)} 2>/dev/null || echo ""`);
    const submitHint = normalizeLightFailure(skillRoot, submitHttp, submitBody, "");
    if (submitHint) {
      throw new Error(submitHint);
    }
    if (submitHttp !== "200" && submitHttp !== "201") {
      throw new Error(`免登录轻量接口 URL 提交失败 (HTTP ${submitHttp}): ${submitBody}`);
    }

    const submitResp = JSON.parse(submitBody);
    if (submitResp.code !== 0 || !submitResp.data || !submitResp.data.task_id) {
      throw new Error(`免登录轻量接口 URL 提交失败: ${submitResp.msg || submitBody}`);
    }

    log("已提交远程文档 URL 到免登录轻量接口，开始轮询结果...", 2);
    const pollRespPath = `${workDir}/light_url_poll.json`;
    let pollCount = 0;
    let markdownUrl = "";
    let finalPollResponse = null;

    while (pollCount < options.pollMax && !markdownUrl) {
      sh(`/bin/sleep ${options.pollSleep}`);
      pollCount += 1;
      const pollHttp = sh(`/usr/bin/curl -s ${shellQuote(LIGHT_API_BASE + "/parse/" + submitResp.data.task_id)} -w '%{http_code}' -o ${shellQuote(pollRespPath)}`).trim();
      const pollBody = sh(`/bin/cat ${shellQuote(pollRespPath)} 2>/dev/null || echo ""`);
      const pollHint = normalizeLightFailure(skillRoot, pollHttp, pollBody, "");
      if (pollHint) {
        throw new Error(pollHint);
      }
      if (pollHttp !== "200" && pollHttp !== "201") {
        throw new Error(`免登录轻量接口 URL 轮询失败 (HTTP ${pollHttp}): ${pollBody}`);
      }

      const pollResp = JSON.parse(pollBody);
      finalPollResponse = pollResp;
      if (pollResp.code !== 0 || !pollResp.data) {
        throw new Error(`免登录轻量接口 URL 轮询失败: ${pollResp.msg || pollBody}`);
      }
      if (pollResp.data.state === "done" && pollResp.data.markdown_url) {
        markdownUrl = pollResp.data.markdown_url;
        break;
      }
      if (pollResp.data.state === "failed") {
        const normalized = normalizeLightFailure(skillRoot, pollHttp, pollBody, pollResp.data.err_msg || "");
        if (normalized) {
          throw new Error(normalized);
        }
        throw new Error(`免登录轻量接口 URL 解析失败: ${pollResp.data.err_msg || "未知错误"}`);
      }
      if (pollCount % 10 === 0) {
        log(`免登录轻量接口 URL 处理中 (${pollCount}/${options.pollMax})`, 2);
      }
    }

    if (!markdownUrl) {
      throw new Error(`免登录轻量接口 URL 处理超时，已尝试 ${pollCount} 次`);
    }

    const mdFile = `${workDir}/full.md`;
    const mdHttp = sh(`/usr/bin/curl -s -L ${shellQuote(markdownUrl)} -w '%{http_code}' -o ${shellQuote(mdFile)}`).trim();
    if (mdHttp !== "200" && mdHttp !== "201") {
      throw new Error(`下载免登录轻量接口 URL Markdown 失败 (HTTP ${mdHttp})`);
    }
    if (finalPollResponse) {
      writeJsonFile(sh, `${workDir}/light_url_result.json`, finalPollResponse);
    }

    return finalizeResult(sh, skillRoot, workDir, info, mdFile, {
      mode: "light",
      sourceFile: sourceUrl,
      detail: {
        task_id: submitResp.data.task_id,
        markdown_url: markdownUrl,
        source_type: info.sourceType
      }
    }, log);
  } finally {
    sh(`/bin/rm -rf ${shellQuote(workDir)}`);
  }
}

function verifyToken(sh, skillRoot, config) {
  const apiToken = resolveApiToken(sh, config);
  if (!apiToken) {
    return "当前未配置 MinerU Token。默认仍可使用免登录轻量接口。";
  }

  const apiBase = sanitizeConfigValue(config.MINERU_API_BASE) || "https://mineru.net/api/v4";
  const probeTaskId = "00000000-0000-0000-0000-000000000000";
  const probeRespPath = `/tmp/mineru-token-verify-${Date.now()}.json`;
  const probeResult = runShellResult(`/usr/bin/curl -sS --connect-timeout 10 --max-time 20 ${shellQuote(apiBase + "/extract/task/" + probeTaskId)} ` +
                                     `-H ${shellQuote("Authorization: Bearer " + apiToken)} ` +
                                     `-w '%{http_code}' -o ${shellQuote(probeRespPath)}`);
  const http = String(probeResult.stdout || "").trim();
  const body = readTextFile(probeRespPath);

  if (probeResult.exitCode !== 0) {
    if (http === "401" || http === "403") {
      throw new Error(buildExpiredTokenHelp(skillRoot, http));
    }
    if (http === "000" || !http) {
      return `Token 已读取，但当前无法连接到 ${apiBase}。请检查网络连通性、代理设置或 MINERU_API_BASE 是否可达。` +
             (probeResult.stderr ? ` 诊断信息：${probeResult.stderr}` : "");
    }
    return `Token 已读取，但自检请求未成功完成（curl 退出码 ${probeResult.exitCode}，HTTP ${http || "unknown"}）。` +
           ` 请检查 API 地址或网络连通性。` +
           (probeResult.stderr ? ` 诊断信息：${probeResult.stderr}` : "");
  }

  if (http === "401" || http === "403") {
    throw new Error(buildExpiredTokenHelp(skillRoot, http));
  }
  if (http !== "200" && http !== "404") {
    return `Token 已读取，但自检接口返回 HTTP ${http}。请检查 API 地址或网络连通性。响应：${body}`;
  }
  return `Token 自检通过：已成功携带 Authorization 访问 ${apiBase}。当前脚本会优先使用标准 Token API。`;
}

function convert(source) {
  const sh = runShell;

  const skillRoot = getSkillRoot(sh);
  const config = loadConfig(skillRoot);
  const apiToken = resolveApiToken(sh, config);
  const mode = apiToken ? "token" : "light";
  const info = buildSourceInfo(sh, source, mode, skillRoot);

  const options = {
    apiBase: config.MINERU_API_BASE || "https://mineru.net/api/v4",
    apiToken: apiToken,
    enableOcr: parseBoolean(config.MINERU_ENABLE_OCR, true),
    enableTable: parseBoolean(config.MINERU_ENABLE_TABLE, true),
    enableFormula: parseBoolean(config.MINERU_ENABLE_FORMULA, false),
    languageCode: config.MINERU_LANGUAGE_CODE || "ch",
    modelVersion: resolveTokenModelVersion(config.MINERU_MODEL_VERSION, info.sourceType),
    pageRanges: normalizePageRanges(config.MINERU_PAGE_RANGES),
    pollMax: parseInteger(config.MINERU_POLL_MAX, 20),
    pollSleep: parseInteger(config.MINERU_POLL_SLEEP, 10),
    logLevel: config.MINERU_LOG_LEVEL || "medium"
  };

  const levelMap = { low: 1, medium: 2, high: 3 };
  const currentLevel = levelMap[options.logLevel] || 2;
  const log = (message, level) => {
    if ((level || 1) <= currentLevel) {
      console.log(message);
    }
  };

  log(`开始转换: ${info.fileName}`, 2);
  log(`转换模式: ${mode === "token" ? "标准 Token API" : "免登录轻量接口"}`, 2);
  log(`输入类型: ${info.sourceType}`, 2);

  if (mode === "token") {
    if (info.sourceType === "local_file") {
      return convertLocalFileWithTokenApi(sh, skillRoot, source, info, options, log);
    }
    return convertRemoteUrlWithTokenApi(sh, skillRoot, source, info, options, log);
  }
  if (info.sourceType === "local_file") {
    return convertLocalFileWithLightApi(sh, skillRoot, source, info, options, log);
  }
  return convertRemoteUrlWithLightApi(sh, skillRoot, source, info, options, log);
}

// ===== CLI 入口 =====
function run(argv) {
  try {
    if (!argv || argv.length === 0) {
      return "用法: osascript -l JavaScript convert.js <文件路径或URL...>\n      osascript -l JavaScript convert.js checktoken\n缺少文件路径或 URL 参数";
    }

    const command = argv[0];
    if (command === "--verify-token" || command === "verify-token" || command === "checktoken") {
      const sh = runShell;
      const skillRoot = getSkillRoot(sh);
      const config = loadConfig(skillRoot);
      return verifyToken(sh, skillRoot, config);
    }

    // 支持多个路径传入：遍历 argv 中所有参数，分别转换
    const results = [];
    for (let i = 0; i < argv.length; i++) {
      const source = argv[i];
      if (!source || source.trim() === "") {
        continue;
      }
      const result = convert(source);
      results.push(result);
    }

    if (results.length === 0) {
      return "没有有效的文件路径或 URL";
    }
    if (results.length === 1) {
      return results[0].message;
    }

    // 多个结果汇总
    const successCount = results.filter(r => r.success).length;
    const messages = results.map((r, idx) => `(${idx + 1}) ${r.message}`).join("\n");
    return `\n========== 批量转换结果 ==========\n${messages}\n==================================\n成功: ${successCount}/${results.length}`;
  } catch (error) {
    return `转换失败: ${error.message}`;
  }
}
