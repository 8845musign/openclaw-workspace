#!/usr/bin/env node
import { t as createDefaultDeps } from "/home/hiroki-yokouchi/.local/share/mise/installs/node/24.18.0/lib/node_modules/openclaw/dist/deps-Ohpw1HsI.js";
import { t as createOutboundSendDeps } from "/home/hiroki-yokouchi/.local/share/mise/installs/node/24.18.0/lib/node_modules/openclaw/dist/outbound-send-deps-BkAAWpG5.js";
import { resolveCommandConfigWithSecrets } from "/home/hiroki-yokouchi/.local/share/mise/installs/node/24.18.0/lib/node_modules/openclaw/dist/command-config-resolution-C1kNUbsZ.js";
import { t as resolveMessageSecretScope } from "/home/hiroki-yokouchi/.local/share/mise/installs/node/24.18.0/lib/node_modules/openclaw/dist/message-secret-scope-ChySUOBS.js";
import { d as getScopedChannelsCommandSecretTargets } from "/home/hiroki-yokouchi/.local/share/mise/installs/node/24.18.0/lib/node_modules/openclaw/dist/command-secret-targets-FYfRsgRi.js";
import { i as getRuntimeConfig } from "/home/hiroki-yokouchi/.local/share/mise/installs/node/24.18.0/lib/node_modules/openclaw/dist/io-By0s-a_s.js";
import { t as ensurePluginRegistryLoaded } from "/home/hiroki-yokouchi/.local/share/mise/installs/node/24.18.0/lib/node_modules/openclaw/dist/runtime-registry-loader-Duw3fvRO.js";
import { c as resolveDefaultAgentId } from "/home/hiroki-yokouchi/.local/share/mise/installs/node/24.18.0/lib/node_modules/openclaw/dist/agent-scope-config-BxAUeF6t.js";
import { runMessageAction } from "/home/hiroki-yokouchi/.local/share/mise/installs/node/24.18.0/lib/node_modules/openclaw/dist/message-action-runner-DxsSz5U6.js";
import { GATEWAY_CLIENT_NAMES, GATEWAY_CLIENT_MODES } from "/home/hiroki-yokouchi/.local/share/mise/installs/node/24.18.0/lib/node_modules/openclaw/dist/client-info-9YxJlXWF.js";
import { createWriteStream } from "node:fs";
import { mkdir, stat, unlink } from "node:fs/promises";
import { dirname } from "node:path";
import { pipeline } from "node:stream/promises";

function parseInput() {
  const raw = process.argv[2];
  if (!raw) {
    throw new Error("JSON input is required.");
  }
  const input = JSON.parse(raw);
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new Error("JSON input must be an object.");
  }
  if (typeof input.action !== "string" || !input.action) {
    throw new Error("input.action is required.");
  }
  return input;
}

async function main() {
  const input = parseInput();
  const params = input.params && typeof input.params === "object" && !Array.isArray(input.params) ? input.params : {};
  const loadedRaw = getRuntimeConfig();
  const scope = resolveMessageSecretScope({
    channel: params.channel ?? input.channel,
    target: params.target ?? params.to,
    targets: params.targets,
    accountId: params.accountId,
  });
  const scopedTargets = getScopedChannelsCommandSecretTargets({
    config: loadedRaw,
    channel: scope.channel,
    accountId: scope.accountId,
  });
  if (scope.channel) {
    ensurePluginRegistryLoaded({ scope: "configured-channels", onlyChannelIds: [scope.channel] });
  } else {
    ensurePluginRegistryLoaded({ scope: "configured-channels" });
  }
  const { effectiveConfig: cfg } = await resolveCommandConfigWithSecrets({
    config: loadedRaw,
    commandName: "message",
    targetIds: scopedTargets.targetIds,
    ...(scopedTargets.allowedPaths ? { allowedPaths: scopedTargets.allowedPaths } : {}),
    autoEnable: true,
  });
  if (input.action === "download-url") {
    const slack = cfg.channels?.slack ?? {};
    let token = slack.userToken ?? slack.botToken;
    if (!token && slack.accounts && typeof slack.accounts === "object") {
      for (const account of Object.values(slack.accounts)) {
        if (!account || typeof account !== "object") {
          continue;
        }
        token = account.userToken ?? account.botToken;
        if (token) {
          break;
        }
      }
    }
    if (!token) {
      throw new Error("Resolved Slack token is unavailable.");
    }
    const url = params.url;
    const dest = params.dest;
    if (typeof url !== "string" || !url.startsWith("https://")) {
      throw new Error("params.url must be an https URL.");
    }
    if (typeof dest !== "string" || !dest) {
      throw new Error("params.dest is required.");
    }
    await mkdir(dirname(dest), { recursive: true });
    const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok || !response.body) {
      throw new Error(`Slack file download failed: ${response.status} ${response.statusText}`);
    }
    try {
      await pipeline(response.body, createWriteStream(dest));
      const fileStat = await stat(dest);
      if (fileStat.size === 0) {
        await unlink(dest).catch(() => {});
        throw new Error("Slack file download returned an empty file.");
      }
    } catch (error) {
      await unlink(dest).catch(() => {});
      throw error;
    }
    process.stdout.write(`${JSON.stringify({ ok: true, path: dest, contentType: response.headers.get("content-type") })}\n`);
    return;
  }
  const deps = createOutboundSendDeps(createDefaultDeps());
  const result = await runMessageAction({
    cfg,
    action: input.action,
    params: {
      ...params,
      channel: params.channel ?? input.channel,
    },
    deps,
    agentId: resolveDefaultAgentId(cfg),
    senderIsOwner: true,
    gateway: {
      clientName: GATEWAY_CLIENT_NAMES.CLI,
      mode: GATEWAY_CLIENT_MODES.CLI,
    },
  });
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error?.stack || error?.message || String(error)}\n`);
  process.exit(1);
});
