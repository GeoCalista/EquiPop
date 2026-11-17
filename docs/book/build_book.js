// build_book.js - compile Book chapters (md subset) to .docx (#19).
// Usage: node build_book.js ch01.md ch02.md ... out.docx
const fs = require("fs");
const path = require("path");
const D = require("docx");

// The pixel size of a PNG or JPEG, read from its header (no packages).
function imageSize(buf) {
  if (buf.readUInt32BE(0) === 0x89504e47)               // PNG: IHDR
    return {type: "png", w: buf.readUInt32BE(16), h: buf.readUInt32BE(20)};
  if (buf[0] === 0xff && buf[1] === 0xd8) {               // JPEG: SOFn
    let o = 2;
    while (o < buf.length) {
      const marker = buf[o + 1], len = buf.readUInt16BE(o + 2);
      if (marker >= 0xc0 && marker <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(marker))
        return {type: "jpg", h: buf.readUInt16BE(o + 5), w: buf.readUInt16BE(o + 7)};
      o += 2 + len;
    }
  }
  throw new Error("not a PNG or JPEG figure");
}

const files = process.argv.slice(2, -1);
const outPath = process.argv[process.argv.length - 1];
const children = [];

children.push(new D.Paragraph({
  heading: D.HeadingLevel.TITLE,
  children: [new D.TextRun("EquiPop: The Book")]}));
children.push(new D.Paragraph({
  children: [new D.TextRun({italics: true,
    text: "Compiled from the repository sources - version " + (process.env.EQP_VERSION || "dev") + ". " +
          "Every example runs; every figure has a script."})]}));

for (const f of files) {
  const lines = fs.readFileSync(f, "utf8").split("\n");
  let i = 0;
  children.push(new D.Paragraph({children: [new D.PageBreak()]}));
  while (i < lines.length) {
    const L = lines[i];
    if (L.startsWith("```")) {                       // code block
      const buf = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        buf.push(lines[i]); i++;
      }
      i++;
      for (const c of buf.length ? buf : [""])
        children.push(new D.Paragraph({
          shading: {type: D.ShadingType.CLEAR, fill: "F2F0EA"},
          spacing: {before: 0, after: 0},
          children: [new D.TextRun({text: c || " ",
            font: "Consolas", size: 18})]}));
      children.push(new D.Paragraph({text: ""}));
      continue;
    }
    const img = L.match(/^!\[(.*)\]\((.*)\)/);
    if (img) {
      const p = path.join(path.dirname(f), img[2]);
      // 17 November 2026: every figure used to be stretched to 620 x 230
      // and declared PNG, whatever it was. Now the type comes from the
      // file and the height keeps the picture's own proportions.
      const data = fs.readFileSync(p);
      const size = imageSize(data);
      const width = 620;
      children.push(new D.Paragraph({
        alignment: D.AlignmentType.CENTER,
        children: [new D.ImageRun({type: size.type, data: data,
          transformation: {width: width,
                           height: Math.round(width * size.h / size.w)}})]}));
      children.push(new D.Paragraph({
        alignment: D.AlignmentType.CENTER,
        children: [new D.TextRun({italics: true, size: 18,
                                  text: "Figure: " + img[1]})]}));
      i++; continue;
    }
    if (L.startsWith("# "))
      children.push(new D.Paragraph({heading: D.HeadingLevel.HEADING_1,
        children: [new D.TextRun(L.slice(2))]}));
    else if (L.startsWith("## "))
      children.push(new D.Paragraph({heading: D.HeadingLevel.HEADING_2,
        children: [new D.TextRun(L.slice(3))]}));
    else if (L.startsWith("- "))
      children.push(new D.Paragraph({bullet: {level: 0},
        children: inline(L.slice(2))}));
    else if (L.trim() === "")
      { /* paragraph break handled by accumulation below */ }
    else {                                           // prose paragraph
      const buf = [L];
      while (i + 1 < lines.length && lines[i + 1].trim() !== "" &&
             !/^(#|```|- |!\[)/.test(lines[i + 1])) { buf.push(lines[++i]); }
      children.push(new D.Paragraph({
        alignment: D.AlignmentType.JUSTIFIED,
        spacing: {after: 160},
        children: inline(buf.join(" "))}));
    }
    i++;
  }
}

function inline(t) {                         // **bold** *italic* `code`
  // 17 November 2026: *italic* was printed with its asterisks; the
  // chapters use it about seventy times.
  const runs = [];
  for (const part of t.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/)) {
    if (!part) continue;
    if (part.startsWith("**"))
      runs.push(new D.TextRun({bold: true, text: part.slice(2, -2)}));
    else if (part.startsWith("*"))
      runs.push(new D.TextRun({italics: true, text: part.slice(1, -1)}));
    else if (part.startsWith("`"))
      runs.push(new D.TextRun({font: "Consolas", size: 20,
                               text: part.slice(1, -1)}));
    else runs.push(new D.TextRun(part));
  }
  return runs;
}

D.Packer.toBuffer(new D.Document({
  styles: {default: {document: {run: {font: "Georgia", size: 22}}}},
  sections: [{properties: {}, children}]})).then(b => {
    fs.writeFileSync(outPath, b);
    console.log("wrote", outPath);
});
