/** Resize/compress an image for storage as a data URL in `.ham/settings.json` (HAM agent avatar). */

const MAX_DATA_URL_CHARS = 350_000;

export async function imageFileToAvatarDataUrl(file: File): Promise<string> {
  if (!file.type.startsWith("image/")) {
    throw new Error("Choose an image file.");
  }
  if (file.size > 8 * 1024 * 1024) {
    throw new Error("Image too large before resize (max 8MB).");
  }
  const bitmap = await createImageBitmap(file);
  const maxSide = 256;
  let { width, height } = bitmap;
  const scale = Math.min(1, maxSide / Math.max(width, height, 1));
  const w = Math.round(width * scale);
  const h = Math.round(height * scale);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    bitmap.close();
    throw new Error("Could not use canvas.");
  }
  ctx.drawImage(bitmap, 0, 0, w, h);
  bitmap.close();
  const dataUrl = canvas.toDataURL("image/jpeg", 0.88);
  if (dataUrl.length > MAX_DATA_URL_CHARS) {
    throw new Error("Avatar still too large after resize; try a smaller image.");
  }
  return dataUrl;
}
