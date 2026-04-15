ObjC.import("Foundation");

function shellQuote(value) {
  return "'" + String(value).replace(/'/g, "'\\''") + "'";
}

function getScriptPath() {
  const args = $.NSProcessInfo.processInfo.arguments;
  if (args.count < 4) {
    throw new Error("无法定位当前脚本路径");
  }
  return ObjC.unwrap(args.objectAtIndex(3));
}

function run(argv) {
  const app = Application.currentApplication();
  app.includeStandardAdditions = true;
  const sh = (cmd) => app.doShellScript(cmd);

  try {
    const scriptPath = getScriptPath();
    const scriptDir = sh(`/usr/bin/dirname ${shellQuote(scriptPath)}`).trim();
    const pythonScript = `${scriptDir}/convert.py`;
    const skillRoot = sh(`/usr/bin/dirname ${shellQuote(scriptDir)}`).trim();
    const uvPath = sh(`/bin/zsh -lc 'command -v uv || true'`).trim();
    const runner = uvPath ? `${shellQuote(uvPath)} run` : "/usr/bin/python3";
    const argList = (argv || []).map(shellQuote).join(" ");
    const command =
      `cd ${shellQuote(skillRoot)} && ${runner} ${shellQuote(pythonScript)}` +
      (argList ? ` ${argList}` : "");

    const output = sh(command);
    console.log(output);
    return output;
  } catch (error) {
    const message =
      "PaddleOCR 转换失败\n" +
      "===============================================\n" +
      `${error.message}\n\n` +
      "建议：\n" +
      "1. 先运行 `uv run scripts/smoke_test.py --skip-api-test`\n" +
      "2. 检查 `config/.env` 是否已配置\n" +
      "3. 直接运行 `uv run scripts/convert.py \"文件路径\"` 查看详细日志";
    console.log(message);
    return message;
  }
}
