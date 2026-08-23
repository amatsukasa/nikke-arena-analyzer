export interface PreparedAnalysisImage {
  file: File;
  preCropped: boolean;
}

export function prepareAnalysisImage(
  file: File,
  options: { maxOutputWidth?: number; filenameSuffix?: string } = {},
): Promise<PreparedAnalysisImage> {
  return new Promise(resolve => {
    const img = new Image();
    const originalUrl = URL.createObjectURL(file);
    const finish = (result: PreparedAnalysisImage) => {
      URL.revokeObjectURL(originalUrl);
      resolve(result);
    };
    img.onload = () => {
      try {
        const scale = Math.min(1, 960 / img.width);
        const width = Math.max(1, Math.round(img.width * scale));
        const height = Math.max(1, Math.round(img.height * scale));
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const context = canvas.getContext("2d", { willReadFrequently: true });
        if (!context) return finish({ file, preCropped: false });
        context.drawImage(img, 0, 0, width, height);
        const pixels = context.getImageData(0, 0, width, height).data;
        const mask = new Uint8Array(width * height);
        for (let index = 0; index < mask.length; index += 1) {
          const offset = index * 4;
          const red = pixels[offset], green = pixels[offset + 1], blue = pixels[offset + 2];
          const maximum = Math.max(red, green, blue), minimum = Math.min(red, green, blue);
          const saturation = maximum === 0 ? 0 : ((maximum - minimum) * 255) / maximum;
          if (maximum > 200 && saturation < 50) mask[index] = 1;
        }
        let best: { x: number; y: number; width: number; height: number; area: number } | null = null;
        const stack: number[] = [];
        for (let start = 0; start < mask.length; start += 1) {
          if (mask[start] !== 1) continue;
          mask[start] = 2; stack.length = 0; stack.push(start);
          let cursor = 0, area = 0, minX = width, maxX = 0, minY = height, maxY = 0;
          while (cursor < stack.length) {
            const current = stack[cursor++], x = current % width, y = Math.floor(current / width);
            area += 1; minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
            for (const neighbour of [x > 0 ? current - 1 : -1, x + 1 < width ? current + 1 : -1, y > 0 ? current - width : -1, y + 1 < height ? current + width : -1]) {
              if (neighbour >= 0 && mask[neighbour] === 1) { mask[neighbour] = 2; stack.push(neighbour); }
            }
          }
          const boxWidth = maxX - minX + 1, boxHeight = maxY - minY + 1;
          if (boxWidth > width * .25 && boxHeight > height * .15 && (!best || area > best.area)) best = { x: minX, y: minY, width: boxWidth, height: boxHeight, area };
        }
        if (!best) return finish({ file, preCropped: false });
        const sourceX = Math.max(0, Math.floor(best.x / scale));
        const sourceY = Math.max(0, Math.floor(best.y / scale));
        const sourceWidth = Math.min(img.width - sourceX, Math.ceil(best.width / scale));
        const sourceHeight = Math.min(img.height - sourceY, Math.ceil(best.height / scale));
        const outputScale = options.maxOutputWidth && sourceWidth > options.maxOutputWidth ? options.maxOutputWidth / sourceWidth : 1;
        const output = document.createElement("canvas");
        output.width = Math.max(1, Math.round(sourceWidth * outputScale));
        output.height = Math.max(1, Math.round(sourceHeight * outputScale));
        const outputContext = output.getContext("2d");
        if (!outputContext) return finish({ file, preCropped: false });
        outputContext.imageSmoothingEnabled = true;
        outputContext.imageSmoothingQuality = "high";
        outputContext.drawImage(img, sourceX, sourceY, sourceWidth, sourceHeight, 0, 0, output.width, output.height);
        output.toBlob(blob => {
          if (!blob) return finish({ file, preCropped: false });
          const suffix = options.filenameSuffix ?? ".modal.png";
          const name = /\.[^.]+$/.test(file.name) ? file.name.replace(/\.[^.]+$/, suffix) : `${file.name}${suffix}`;
          finish({ file: new File([blob], name, { type: "image/png", lastModified: Date.now() }), preCropped: true });
        }, "image/png");
      } catch {
        finish({ file, preCropped: false });
      }
    };
    img.onerror = () => finish({ file, preCropped: false });
    img.src = originalUrl;
  });
}
