/*
  SuperDoc renders nothing in the page itself. Every document is parsed and laid
  out in a module Web Worker that @superdoc/docx-engine spawns with

      new Worker(new URL('./assets/browser-worker-entry-<hash>.js', import.meta.url))

  Next.js does not emit worker assets for a dependency reached through a dynamic
  import, so that URL 404s, the worker never starts, and every document fails to
  open with "the background document worker could not start".

  SuperDoc's documented answer is the workerUrls config: same-origin URLs the
  application serves itself. This copies the two workers we use out of the
  package and into public/superdoc under stable names, so the filename hash
  changing on an upgrade cannot silently break the editor. The collaboration
  worker is deliberately not copied: nothing here uses real-time collaboration,
  and it is 9.4 MB.
*/
import { copyFileSync, existsSync, mkdirSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = join(here, "..", "node_modules", "@superdoc", "docx-engine", "dist", "assets");
const target = join(here, "..", "public", "superdoc");

const WANTED = [
  ["browser-worker-entry-", "document-worker.js"],
  ["review-index-worker-entry-", "review-index-worker.js"],
];

if (!existsSync(source)) {
  console.error(`SuperDoc worker assets are not at ${source}. Run npm install first.`);
  process.exit(1);
}

mkdirSync(target, { recursive: true });
const available = readdirSync(source);

for (const [prefix, stableName] of WANTED) {
  const found = available.find((name) => name.startsWith(prefix) && name.endsWith(".js"));
  if (!found) {
    console.error(`No SuperDoc worker matching ${prefix}* in ${source}.`);
    process.exit(1);
  }
  const to = join(target, stableName);
  copyFileSync(join(source, found), to);
  const mb = (statSync(to).size / 1024 / 1024).toFixed(1);
  console.log(`superdoc worker: ${found} -> public/superdoc/${stableName} (${mb} MB)`);
}
