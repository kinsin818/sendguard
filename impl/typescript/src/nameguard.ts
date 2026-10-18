/**
 * The reserved-device-name guard.
 *
 * spec/canonical.md section 10 names the class; this is the MS Learn device table
 * that class refers to. The guard exists so that no probe in this port ever OPENS
 * one of these names for reading: reading a reserved name can block forever on the
 * device behind it, and an unkillable read would cost the cell its evidence.
 * Creating and listing such a name is allowed -- that is what the traps measure.
 */

const RESERVED_BASES: readonly string[] = ["CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"];

const COM_INDEX = /^COM[1-9]$/;
const LPT_INDEX = /^LPT[1-9]$/;

/** Last path component, on either separator, without touching the filesystem. */
export function baseName(name: string): string {
  const cut = Math.max(name.lastIndexOf("\\"), name.lastIndexOf("/"));
  return cut < 0 ? name : name.slice(cut + 1);
}

/** True when opening this name routes to a device rather than to a file. */
export function isReservedDeviceName(name: string): boolean {
  const base = baseName(name).toUpperCase();
  const dot = base.indexOf(".");
  const stem = dot < 0 ? base : base.slice(0, dot);
  return RESERVED_BASES.includes(stem) || COM_INDEX.test(stem) || LPT_INDEX.test(stem);
}

/**
 * Reason the extended-prefix (`\\?\`) OS-legality probe must not run for this name,
 * or null when it may. A `\\?\` create of a reserved name lands a REAL NTFS entry
 * that plain-path tools then open as a device; leaving it inside a shared clone is a
 * hazard for the next lane and project rule forbids this port from deleting it.
 */
export function extendedProbeRefusal(name: string): string | null {
  return isReservedDeviceName(name)
    ? "not-probed: reserved device name; an extended-prefix create would land a real entry that plain-path tools open as a device, and project rule forbids deletion by this port"
    : null;
}
