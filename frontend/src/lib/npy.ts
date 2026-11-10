/** Minimal reader for the .npy files written by numpy.save (2-D float arrays). */
export interface NpyArray {
  data: Float32Array;
  shape: number[];
}

export function parseNpy(buffer: ArrayBuffer): NpyArray {
  const bytes = new Uint8Array(buffer);
  const magic = String.fromCharCode(...bytes.slice(1, 6));
  if (bytes[0] !== 0x93 || magic !== "NUMPY") {
    throw new Error("Not a .npy file");
  }
  const view = new DataView(buffer);
  const major = bytes[6];
  const headerLength = major === 1 ? view.getUint16(8, true) : view.getUint32(8, true);
  const headerStart = major === 1 ? 10 : 12;
  const header = new TextDecoder("latin1").decode(bytes.slice(headerStart, headerStart + headerLength));

  const descr = /'descr':\s*'([^']+)'/.exec(header)?.[1] ?? "<f4";
  const fortran = /'fortran_order':\s*True/.test(header);
  const shapeText = /'shape':\s*\(([^)]*)\)/.exec(header)?.[1] ?? "";
  const shape = shapeText
    .split(",")
    .map((piece) => piece.trim())
    .filter(Boolean)
    .map(Number);

  const dataStart = headerStart + headerLength;
  const length = shape.reduce((total, dimension) => total * dimension, 1);

  if (fortran) throw new Error("Fortran-ordered arrays are not supported");
  if (shape.length === 0) throw new Error("Empty array shape");

  let data: Float32Array;
  if (descr === "<f4" || descr === "|f4") {
    data = new Float32Array(buffer.slice(dataStart, dataStart + length * 4));
  } else if (descr === "<f8" || descr === "|f8") {
    const wide = new Float64Array(buffer.slice(dataStart, dataStart + length * 8));
    data = Float32Array.from(wide);
  } else if (descr === "|u1" || descr === "<u1") {
    const raw = new Uint8Array(buffer.slice(dataStart, dataStart + length));
    data = Float32Array.from(raw);
  } else {
    throw new Error(`Unsupported .npy dtype: ${descr}`);
  }

  return { data, shape };
}
