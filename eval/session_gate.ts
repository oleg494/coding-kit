import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import type { ExtensionAPI } from '@oh-my-pi/pi-coding-agent';

// Experiment-only tool boundary. This is not an OS sandbox: it bounds the
// read/write tools exposed to the model in a frozen workspace. Shell, network,
// and URI tools are never offered, and tool paths are checked against real
// filesystem ancestors so symlinks cannot escape the workspace.
export default function (pi: ExtensionAPI) {
  const root = fs.realpathSync(process.env.SESSION_GATE_ROOT!);
  const logPath = process.env.SESSION_GATE_LOG!;
  const marker = process.env.SESSION_GATE_POLICY_MARKER ?? '';
  if (!logPath) throw new Error('SESSION_GATE_LOG is required');

  const inside = (base: string, target: string) => {
    const rel = path.relative(base, target);
    return rel === '' || (rel !== '..' && !rel.startsWith(`..${path.sep}`) && !path.isAbsolute(rel));
  };

  const nearestReal = (target: string): string | null => {
    const resolvedTarget = path.resolve(target);
    if (!inside(root, resolvedTarget)) return resolvedTarget;
    const rel = path.relative(root, resolvedTarget);
    if (rel === '') return root;
    let cur = root;
    let lastReal = root;
    for (const part of rel.split(path.sep)) {
      cur = path.join(cur, part);
      const st = fs.lstatSync(cur, { throwIfNoEntry: false });
      if (!st) break;
      try {
        lastReal = fs.realpathSync(cur);
      } catch {
        return null;
      }
      if (!inside(root, lastReal)) return lastReal;
    }
    return lastReal;
  };

  const emit = (event: unknown) => fs.appendFileSync(logPath, JSON.stringify(event) + '\n');

  type Writable = { base: string; dir: boolean; real: string };
  const writable: Writable[] = (JSON.parse(process.env.SESSION_GATE_WRITABLE ?? '[]') as Array<{ path: string; dir?: boolean }>)
    .map((item) => {
      const base = path.resolve(String(item.path));
      if (!inside(root, base)) throw new Error(`writable path escapes root: ${base}`);
      const real = nearestReal(base);
      if (!real || !inside(root, real)) throw new Error(`writable real path escapes root: ${base}`);
      return { base, dir: item.dir === true, real };
    });

  const normalize = (value: unknown, isRead: boolean): string | null => {
    if (typeof value !== 'string' || value.length === 0) return null;
    if (value.includes('\0') || value.includes('://') || value.includes('?') || value.includes('#')) return null;
    if (/^[A-Za-z]:/.test(value) || value.startsWith('/') || value.startsWith('\\') || value.startsWith('~')) return null;
    let body = value;
    if (isRead) body = body.replace(/:(?:raw|\d+[+\d,-]*|-\d+)(?::raw)?$/, '');
    if (body.includes(':')) return null;
    const rawParts = body.replace(/\\/g, '/').split('/');
    if (rawParts.includes('..')) return null;
    const parts = rawParts.filter((part) => part !== '' && part !== '.');
    if (parts.some((part) => part.endsWith(' ') || part.endsWith('.'))) return null;
    // An empty result names the workspace root itself; reads are always inside it,
    // while root writes still need an explicit root entry in the writable list.
    return parts.join('/');
  };

  const writableTarget = (target: string, real: string): boolean => {
    return writable.some((entry) => {
      if (entry.dir) return inside(entry.base, target) && inside(entry.real, real);
      const entryReal = nearestReal(entry.base);
      return Boolean(entryReal) && inside(entry.base, target) && inside(target, entry.base) && inside(entryReal!, real) && inside(real, entryReal!);
    });
  };

  pi.on('before_agent_start', async (_event, ctx) => {
    // OMP may return the assembled system prompt as string[] (base prompt and
    // injected project/policy sections). Join before matching or hashing so the
    // policy marker check and prompt digest work for both shapes.
    const raw: unknown = ctx.getSystemPrompt();
    const system = Array.isArray(raw) ? raw.map((part) => String(part)).join('\n') : String(raw ?? '');
    emit({
      type: 'gate_ready',
      root,
      policy_marker: Boolean(marker),
      policy_loaded: Boolean(marker) && system.includes(marker),
      system_sha256: createHash('sha256').update(system).digest('hex'),
      system_chars: system.length,
      tools: pi.getActiveTools(),
    });
  });

  pi.on('tool_call', async (event) => {
    const name = event.toolName;
    const toolCallId = 'toolCallId' in event && typeof event.toolCallId === 'string' ? event.toolCallId : null;
    if (name === 'todo') {
      emit({ type: 'tool_call', name, toolCallId, allowed: true, reason: 'todo is not a file tool' });
      return;
    }
    if (name !== 'read' && name !== 'write') {
      emit({ type: 'tool_call', name, toolCallId, allowed: false, reason: 'tool not in allowlist' });
      return { block: true, reason: 'Only read, write, and todo are available in this frozen workspace.' };
    }
    const input = event.input as { path?: unknown } | undefined;
    const normalized = normalize(input?.path, name === 'read');
    if (normalized === null) {
      emit({ type: 'tool_call', name, toolCallId, path: input?.path, allowed: false, reason: 'unsafe path or URI' });
      return { block: true, reason: 'Use a plain relative workspace path; URIs, absolute paths, queries, and traversal are denied.' };
    }
    const target = path.resolve(root, normalized);
    const link = fs.lstatSync(target, { throwIfNoEntry: false });
    if (link?.isSymbolicLink()) {
      let resolved: string | undefined;
      try {
        resolved = fs.realpathSync(target);
      } catch {
        resolved = undefined;
      }
      if (!resolved) {
        emit({ type: 'tool_call', name, toolCallId, path: input?.path, normalized, allowed: false, reason: 'broken symlink' });
        return { block: true, reason: 'Symbolic links must resolve inside the frozen workspace.' };
      }
    }
    const real = nearestReal(target);
    if (real === null) {
      emit({ type: 'tool_call', name, toolCallId, path: input?.path, normalized, allowed: false, reason: 'broken symlink' });
      return { block: true, reason: 'Symbolic links must resolve inside the frozen workspace.' };
    }
    const contained = inside(root, target) && inside(root, real);
    const allowed = contained && (name === 'read' || writableTarget(target, real));
    emit({
      type: 'tool_call', name, toolCallId, path: input?.path, normalized, allowed,
      reason: !contained ? 'outside workspace' : (allowed ? 'inside workspace' : 'path is not writable'),
    });
    if (!allowed) {
      return {
        block: true,
        reason: name === 'read'
          ? 'Reads are limited to the frozen workspace.'
          : 'Writes are limited to declared writable paths inside the frozen workspace.',
      };
    }
  });
}
