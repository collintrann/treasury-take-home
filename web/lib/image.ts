// Matches the checker's own downscale, so nothing it would use is lost, and
// keeps uploads well under the host's 4.5 MB request limit.
const MAX_EDGE = 1568;
const JPEG_QUALITY = 0.88;

export async function shrinkForUpload(file: File): Promise<File> {
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    // The browser can't decode it (e.g. HEIC in some browsers); let the checker judge it.
    return file;
  }
  const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height));
  const width = Math.round(bitmap.width * scale);
  const height = Math.round(bitmap.height * scale);
  const canvas = new OffscreenCanvas(width, height);
  const ctx = canvas.getContext("2d")!;
  // JPEG has no transparency; without a white backing, clear areas turn black.
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, width, height);
  ctx.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();
  const blob = await canvas.convertToBlob({ type: "image/jpeg", quality: JPEG_QUALITY });
  return new File([blob], file.name, { type: "image/jpeg" });
}
