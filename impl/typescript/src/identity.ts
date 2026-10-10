/**
 * Cell identity and the filename rule, per spec/cell-identity.md sections 1 and 3.
 *
 * Identity for cross-port comparison is (case_group, case_id, sub_identity).
 * sub_identity is an ORDERED, NAMED set of extra dimensions, and a dimension that
 * varies must also appear as a named field inside the cell -- encoding it only in
 * the filename is what produced the 48 length collisions the patch names.
 *
 * Rendering used here: dimensions joined by ".", each dimension "name-value".
 * A value may not contain "."; a name may not contain "." or "-". The split is on
 * the first "-" of each segment, so a value may contain "-". That makes the filename
 * reversible. Parse with parseSubIdentity().
 */

export interface Dim {
  readonly name: string;
  readonly value: string | number;
}

export function renderSubIdentity(dims: readonly Dim[]): string {
  if (dims.length === 0) return "";
  for (const d of dims) {
    if (String(d.value).includes(".") || d.name.includes(".") || d.name.includes("-")) {
      throw new Error(`dimension name/value not renderable: ${d.name}=${String(d.value)}`);
    }
  }
  return dims.map((d) => `${d.name}-${String(d.value)}`).join(".");
}

export function parseSubIdentity(sub: string): Dim[] {
  if (sub === "") return [];
  return sub.split(".").map((part) => {
    const cut = part.indexOf("-");
    if (cut < 1) throw new Error(`sub_identity segment is not name-value: ${part}`);
    const name = part.slice(0, cut);
    const value = part.slice(cut + 1);
    return { name, value: /^\d+$/.test(value) ? Number(value) : value };
  });
}

/** `results/<lang>.<os>.<arch>/<case_group>__<case_id>[__<sub_identity>].json` */
export function cellFileName(caseGroup: string, caseId: string, dims: readonly Dim[]): string {
  const sub = renderSubIdentity(dims);
  const core = sub === "" ? `${caseGroup}__${caseId}` : `${caseGroup}__${caseId}__${sub}`;
  if (/[<>:"|?*]/.test(core) || /[. ]$/.test(core)) {
    throw new Error(`cell filename would itself be an illegal Windows name: ${core}`);
  }
  return `${core}.json`;
}

/** The equality key, without api_entry (section 1: api_entry is data, not identity). */
export function equalityKey(caseGroup: string, caseId: string, dims: readonly Dim[]): readonly (string | number)[] {
  return [caseGroup, caseId, renderSubIdentity(dims)] as const;
}
