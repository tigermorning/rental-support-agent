// 서비스 저장소의 법적 고지(src/lib/legal/*.ts)를 docs/*.md 로 추출한다.
// 사용법: node scripts/export_docs.mjs <korea-direct-rental 경로>
// 원본 .ts 는 확장자 없는 import 와 "@/" 별칭을 쓰므로 해석 훅으로 .ts 를 붙여 준다.
import { execSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { registerHooks } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const src = resolve(process.argv[2] ?? "../korea-direct-rental");
const srcRoot = join(src, "src");

registerHooks({
  resolve(specifier, context, next) {
    let spec = specifier;
    if (spec.startsWith("@/")) spec = pathToFileURL(join(srcRoot, spec.slice(2))).href;
    if ((spec.startsWith(".") || spec.startsWith("file:")) && !/\.[cm]?[jt]s$/.test(spec)) {
      const base = spec.startsWith("file:") ? fileURLToPath(spec) : join(dirname(fileURLToPath(context.parentURL)), spec);
      if (existsSync(base + ".ts")) return next(pathToFileURL(base + ".ts").href, context);
    }
    return next(spec, context);
  },
});

const { LEGAL_DOCS } = await import(pathToFileURL(join(srcRoot, "lib", "legal", "index.ts")).href);
const commit = execSync("git rev-parse --short HEAD", { cwd: src }).toString().trim();

function renderBlock(b) {
  if ("p" in b) return b.p;
  if ("note" in b) return `> ${b.note}`;
  if ("ul" in b) return b.ul.map((x) => `- ${x}`).join("\n");
  if ("table" in b) {
    const row = (r) => `| ${r.join(" | ")} |`;
    return [row(b.table.head), row(b.table.head.map(() => "---")), ...b.table.rows.map(row)].join("\n");
  }
  throw new Error(`알 수 없는 블록: ${JSON.stringify(b)}`);
}

const outDir = join(dirname(fileURLToPath(import.meta.url)), "..", "docs");
mkdirSync(outDir, { recursive: true });
for (const doc of LEGAL_DOCS) {
  const parts = [
    `# ${doc.title}`,
    `<!-- 원본: korea-direct-rental@${commit} src/lib/legal (slug: ${doc.slug}). 직접 고치지 말고 scripts/export_docs.mjs 로 다시 추출 -->`,
    `시행일: ${doc.effectiveDate}`,
    ...(doc.intro ?? []),
  ];
  for (const s of doc.sections) parts.push(`## ${s.heading}`, ...s.blocks.map(renderBlock));
  const file = join(outDir, `${doc.slug}.md`);
  writeFileSync(file, parts.join("\n\n") + "\n", "utf8");
  console.log(`${doc.slug}.md  섹션 ${doc.sections.length}개`);
}
console.log(`원본 커밋 ${commit}`);
