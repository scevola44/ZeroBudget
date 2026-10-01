// YNAB exports are comma-separated with optional "quoted" fields. A line with
// N commas outside quotes yields N + 1 fields (a trailing comma adds an empty
// one), so the loop must stop once no separator follows a field.
export function parseCsvLine(line: string): string[] {
  const fields: string[] = [];
  let i = 0;
  while (i <= line.length) {
    if (line[i] === '"') {
      i++;
      let field = "";
      while (i < line.length) {
        if (line[i] === '"' && line[i + 1] === '"') {
          field += '"';
          i += 2;
        } else if (line[i] === '"') {
          i++;
          break;
        } else {
          field += line[i++];
        }
      }
      fields.push(field);
      if (line[i] !== ",") break;
      i++;
    } else {
      let field = "";
      while (i < line.length && line[i] !== ",") field += line[i++];
      fields.push(field.trim());
      if (line[i] !== ",") break;
      i++;
    }
  }
  return fields;
}
